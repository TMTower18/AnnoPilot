from pathlib import Path
from typing import List, Optional, Union
import csv
import io
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db, UPLOADS, EXPORTS
from app.models import Dataset,Sample,Settings,SamplingRun,SampleSelection,Reviewer,ReviewAssignment
from app.schemas import ScoringSettings,SamplingRequest,ReviewerRequest,ReviewRequest
from app.services.pipeline import get_settings,store_files,import_dataset,analyze_dataset,sample_dict,dataset_dict,choose_samples,balance

router = APIRouter(prefix='/api')

def require(db,model,id):
    item = db.get(model,id)
    if item is None:
        raise HTTPException(404,model.__name__+' not found')
    return item

def latest_run(db,dataset_id):
    return db.scalar(select(SamplingRun).where(SamplingRun.dataset_id==dataset_id).order_by(SamplingRun.id.desc()))

def run_dict(db,run,dataset):
    if not run:
        return None
    return dict(id=run.id,config=run.config,needs_regeneration=run.revision!=dataset.revision,selections=[dict(**sample_dict(require(db,Sample,x.sample_id)),sampling_reason=x.reason) for x in run.selections])

def assignment_dict(db,a):
    selection = require(db,SampleSelection,a.selection_id)
    s = require(db,Sample,selection.sample_id)
    return dict(**sample_dict(s),assignment_id=a.id,reviewer_id=a.reviewer_id,reviewer=require(db,Reviewer,a.reviewer_id).name,status=a.status,note=a.note,sampling_reason=selection.reason,needs_regeneration=a.revision!=require(db,Dataset,s.dataset_id).revision)

@router.get('/health')
def health():
    return {'status':'ok','application':'AnnoPilot'}

@router.get('/datasets')
def datasets(db:Session=Depends(get_db)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]

@router.post('/datasets/upload')
async def upload(name:str=Form(...),format:str=Form('AUTO'),task_type:str=Form('AUTO'),annotations:List[UploadFile]=File(...),media:Optional[List[Union[UploadFile,str]]]=File(None),db:Session=Depends(get_db)):
    if not name.strip() or len(name)>200:
        raise HTTPException(422,'Dataset name must contain 1–200 characters')
    if task_type not in ('AUTO','BBOX_2D','SEGMENTATION','KEYPOINT','CUBOID_3D'):
        raise HTTPException(422,'Unsupported annotation task')
    if any(isinstance(file,str) and file for file in (media or [])):
        raise HTTPException(422,'Media must be uploaded files')
    folder = UPLOADS / uuid.uuid4().hex
    try:
        annotation_paths = await store_files(annotations,folder/'annotations')
        media_paths = await store_files([file for file in (media or []) if not isinstance(file,str) and file.filename],folder/'media')
        dataset = import_dataset(db,name,format,task_type,annotation_paths,media_paths)
        dataset.storage_key = folder.name
        db.commit()
        return dataset_dict(dataset)
    except (ValueError,KeyError,TypeError,OSError,ET.ParseError,zipfile.BadZipFile) as e:
        db.rollback()
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(422,'Import failed: '+str(e))
    except Exception:
        db.rollback()
        shutil.rmtree(folder,ignore_errors=True)
        raise

@router.get('/datasets/{id}')
def dataset(id:int,db:Session=Depends(get_db)):
    return dataset_dict(require(db,Dataset,id))

@router.delete('/datasets/{id}')
def delete_dataset(id:int,db:Session=Depends(get_db)):
    dataset = require(db,Dataset,id)
    folders = {Path(s.media_path).relative_to(UPLOADS).parts[0] for s in dataset.samples if s.media_path and Path(s.media_path).is_relative_to(UPLOADS)}
    if dataset.storage_key:
        folders.add(dataset.storage_key)
    db.delete(dataset)
    db.commit()
    for folder in folders:
        shutil.rmtree(UPLOADS/folder,ignore_errors=True)
    return {'deleted':id}

@router.get('/datasets/{id}/samples')
def samples(id:int,db:Session=Depends(get_db)):
    return [sample_dict(s) for s in require(db,Dataset,id).samples]

@router.get('/samples/{id}')
def sample_detail(id:int,db:Session=Depends(get_db)):
    s = require(db,Sample,id)
    return dict(**sample_dict(s,True),dataset_id=s.dataset_id,source_format=require(db,Dataset,s.dataset_id).format)

@router.get('/samples/{id}/media')
def media_file(id:int,db:Session=Depends(get_db)):
    s = require(db,Sample,id)
    if not s.media_path or not Path(s.media_path).is_file():
        raise HTTPException(404,'Media unavailable')
    return FileResponse(s.media_path)

@router.get('/settings')
def settings(db:Session=Depends(get_db)):
    return get_settings(db).model_dump()

@router.put('/settings')
def save_settings(config:ScoringSettings,db:Session=Depends(get_db)):
    row = db.get(Settings,1)
    if row:
        row.config=config.model_dump()
    else:
        db.add(Settings(id=1,config=config.model_dump()))
    # Recalculate atomically; existing selections and assignments remain preserved but stale.
    for d in db.scalars(select(Dataset)):
        analyze_dataset(db,d,config)
        d.revision+=1
    db.commit()
    return config.model_dump()

@router.post('/datasets/{id}/recalculate')
def recalculate(id:int,db:Session=Depends(get_db)):
    d = require(db,Dataset,id)
    analyze_dataset(db,d)
    d.revision+=1
    db.commit()
    return dataset_dict(d)

@router.get('/datasets/{id}/sampling')
def sampling(id:int,db:Session=Depends(get_db)):
    return run_dict(db,latest_run(db,id),require(db,Dataset,id))

@router.post('/datasets/{id}/sampling')
def generate_sampling(id:int,config:SamplingRequest,db:Session=Depends(get_db)):
    d = require(db,Dataset,id)
    if not d.samples:
        raise HTTPException(422,'Dataset has no samples')
    chosen = choose_samples(d.samples,config)
    run = SamplingRun(dataset_id=id,revision=d.revision,config=config.model_dump())
    run.selections = [SampleSelection(sample_id=s,reason=r) for s,r in chosen.items()]
    db.add(run)
    db.commit()
    return run_dict(db,run,d)

@router.get('/datasets/{id}/reviewers')
def reviewers(id:int,db:Session=Depends(get_db)):
    return [dict(id=r.id,name=r.name) for r in require(db,Dataset,id).reviewers]

@router.post('/datasets/{id}/reviewers')
def add_reviewer(id:int,config:ReviewerRequest,db:Session=Depends(get_db)):
    d = require(db,Dataset,id)
    name = config.name.strip()
    if not name or any(r.name.casefold()==name.casefold() for r in d.reviewers):
        raise HTTPException(422,'Reviewer name must be nonempty and unique within dataset')
    r = Reviewer(dataset_id=id,name=name)
    db.add(r)
    db.commit()
    return dict(id=r.id,name=r.name)

@router.delete('/reviewers/{id}')
def remove_reviewer(id:int,db:Session=Depends(get_db)):
    r = require(db,Reviewer,id)
    if any(a.status!='PENDING' or a.note for a in r.assignments):
        raise HTTPException(409,'Reviewer has saved review results; preserve the reviewer to retain results')
    db.delete(r)
    db.commit()
    return {'deleted':id}

@router.post('/datasets/{id}/balance')
def balance_workload(id:int,db:Session=Depends(get_db)):
    d = require(db,Dataset,id)
    run = latest_run(db,id)
    if not run or not run.selections:
        raise HTTPException(422,'Generate a QC subset first')
    if run.revision != d.revision:
        raise HTTPException(409,'QC subset needs regeneration after recalculation')
    if not d.reviewers:
        raise HTTPException(422,'Add at least one reviewer')
    if any(x.assignment and (x.assignment.status!='PENDING' or x.assignment.note) for x in run.selections):
        raise HTTPException(409,'This subset has saved reviews. Generate a new subset to rebalance; previous results remain exportable.')
    try:
        assignments = balance([require(db,Sample,x.sample_id) for x in run.selections],sorted(d.reviewers,key=lambda r:r.id))
    except ValueError as error:
        raise HTTPException(422,str(error))
    for x in run.selections:
        if x.assignment:
            if x.assignment.status=='PENDING' and not x.assignment.note:
                x.assignment.reviewer_id=assignments[x.sample_id]
                x.assignment.revision=d.revision
        else:
            x.assignment = ReviewAssignment(reviewer_id=assignments[x.sample_id],revision=d.revision)
    db.commit()
    return [assignment_dict(db,x.assignment) for x in run.selections]

@router.get('/datasets/{id}/assignments')
def assignments(id:int,db:Session=Depends(get_db)):
    require(db,Dataset,id)
    run = latest_run(db,id)
    return [assignment_dict(db,x.assignment) for x in run.selections if x.assignment] if run else []

@router.get('/reviewers/{id}/queue')
def queue(id:int,db:Session=Depends(get_db)):
    r = require(db,Reviewer,id)
    run = latest_run(db,r.dataset_id)
    rows = [assignment_dict(db,x.assignment) for x in run.selections if x.assignment and x.assignment.reviewer_id==id] if run else []
    return sorted(rows,key=lambda x:(-(x['overall_difficulty'] or 0),x['id']))

@router.put('/assignments/{id}/review')
def review(id:int,result:ReviewRequest,db:Session=Depends(get_db)):
    a = require(db,ReviewAssignment,id)
    a.status=result.status
    a.note=result.note
    db.commit()
    return assignment_dict(db,a)

@router.get('/datasets/{id}/exports/{kind}')
def export(id:int,kind:str,db:Session=Depends(get_db)):
    d = require(db,Dataset,id)
    run = latest_run(db,id)
    if kind=='smart_sample':
        fields=['sample_id','file_name','annotation_type','overall_difficulty','annotation_difficulty','visual_difficulty','difficulty_level','sampling_reason']
        rows = run_dict(db,run,d)['selections'] if run else []
    elif kind in ('review_assignments','review_results'):
        fields=['sample_id','file_name','annotation_type','overall_difficulty','difficulty_level','reviewer'] if kind=='review_assignments' else ['sample_id','file_name','annotation_type','reviewer','overall_difficulty','review_status','note']
        # Results include historical runs so regeneration never hides saved reviews.
        runs = list(db.scalars(select(SamplingRun).where(SamplingRun.dataset_id==id))) if kind=='review_results' else ([run] if run else [])
        rows = [assignment_dict(db,x.assignment) for r in runs for x in r.selections if x.assignment]
    else:
        raise HTTPException(404,'Unknown export')
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=fields)
    writer.writeheader()
    for row in rows:
        row=dict(row,sample_id=row['id'],annotation_type=row['task_type'],difficulty_level=row['level'],review_status=row.get('status'))
        values={k:row.get(k,'') for k in fields}
        # Prevent spreadsheet formula execution when opening user-controlled text.
        values={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in values.items()}
        writer.writerow(values)
    payload=output.getvalue().encode('utf-8-sig')
    (EXPORTS/f'{id}_{kind}.csv').write_bytes(payload)
    return Response(payload,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{kind}.csv"'})
