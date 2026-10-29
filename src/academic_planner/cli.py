import argparse,json
from .generator import Scale, TARGET_SCALE
from .pipeline import run_pipeline
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",default="data/generated"); p.add_argument("--database-url",default=None); p.add_argument("--seed",type=int,default=20261022); p.add_argument("--no-db",action="store_true")
    p.add_argument("--scale",choices=("starter","target"),default="starter")
    p.add_argument("--programs",type=int,default=None)
    p.add_argument("--courses",type=int,default=None)
    p.add_argument("--faculty",type=int,default=None)
    p.add_argument("--student-plans",type=int,default=None)
    p.add_argument("--room-scarcity",action="store_true")
    a=p.parse_args()
    base=TARGET_SCALE if a.scale=="target" else Scale()
    scale=Scale(
        programs=a.programs if a.programs is not None else base.programs,
        courses=a.courses if a.courses is not None else base.courses,
        faculty=a.faculty if a.faculty is not None else base.faculty,
        student_plans=a.student_plans if a.student_plans is not None else base.student_plans,
    )
    print(json.dumps(run_pipeline(
        a.output_dir,a.database_url,a.seed,not a.no_db,scale=scale,
        room_scarcity=a.room_scarcity,
    ),indent=2))
if __name__=="__main__": main()
