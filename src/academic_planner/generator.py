import random, hashlib, json
from dataclasses import asdict, dataclass
from pathlib import Path
import pandas as pd

@dataclass
class Scale:
    programs:int=10
    courses:int=100
    faculty:int=50
    student_plans:int=1000

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


TARGET_SCALE = Scale(programs=100, courses=1000, faculty=500, student_plans=20000)
TARGET_TERM_ID = "2027-SPRING"


def generate_dataset(seed=20261022, scale=None):
    scale=scale or Scale(); r=random.Random(seed)
    depts=["Computing","Engineering","Sciences","Business","Design"]
    programs=[dict(program_id=f"PRG-{i:06d}",name=f"{depts[(i-1)%5]} Program {i:02d}",department=depts[(i-1)%5]) for i in range(1,scale.programs+1)]
    courses=[]
    for i in range(1,scale.courses+1):
        p=programs[(i-1)%len(programs)]; level=min(4,1+(i-1)//max(1,scale.courses//4))
        courses.append(dict(course_id=f"CRS-{i:06d}",program_id=p["program_id"],code=f"{i:04d}",title=f"{['Foundations','Applied','Advanced','Special Topics'][level-1]} Course {i:03d}",credits=r.choice([2,3,3,4]),course_level=level,is_elective=i%5==0))
    prereqs=[]
    for i in range(11,scale.courses+1):
        if r.random()<.22:
            prereqs.append(dict(prerequisite_id=f"PRQ-{len(prereqs)+1:06d}",course_id=f"CRS-{i:06d}",prerequisite_course_id=f"CRS-{r.randint(1,i-1):06d}",effective_from="2026-01-01",effective_to=None))
    faculty=[]; skills=[]; availability=[]
    for i in range(1,scale.faculty+1):
        status="ON_LEAVE" if i%17==0 else "ACTIVE"
        faculty.append(dict(faculty_id=f"FAC-{i:06d}",name=f"Faculty Member {i:03d}",department=depts[(i-1)%5],max_weekly_hours=r.choice([8,10,12,14,16]),employment_status=status))
        for c in r.sample(courses,k=min(len(courses),r.randint(3,8))):
            skills.append(dict(faculty_skill_id=f"FSK-{len(skills)+1:06d}",faculty_id=f"FAC-{i:06d}",course_id=c["course_id"],skill_level=r.randint(2,5),effective_from="2026-01-01",effective_to=None))
        for day in range(5):
            for slot in range(1,5):
                availability.append(dict(availability_id=f"AVL-{len(availability)+1:07d}",faculty_id=f"FAC-{i:06d}",term_id=TARGET_TERM_ID,day_of_week=day,slot_id=f"S{slot}",available=status=="ACTIVE" and r.random()>.12,effective_from="2026-08-01",effective_to=None))
    rooms=[dict(room_id=f"ROM-{i:06d}",building=f"Building {(i-1)//6+1}",room_type="LAB" if i%4==0 else "LECTURE",capacity=[25,30,40,50,60,80][(i-1)%6],active=True) for i in range(1,31)]
    plans=[]
    for i in range(1,scale.student_plans+1):
        plans.append(dict(student_plan_id=f"STP-{i:07d}",student_id=f"STD-{i:07d}",program_id=programs[(i-1)%len(programs)]["program_id"],term_id=TARGET_TERM_ID,year_of_study=r.randint(1,4),created_at="2026-10-01"))
    interests=[]
    weights=[5 if c["is_elective"] else 1 for c in courses]
    for p in plans:
        count=r.randint(2,5); chosen=[]
        for c in r.choices(courses,weights=weights,k=count*3):
            if c not in chosen: chosen.append(c)
            if len(chosen)>=count: break
        for c in chosen:
            eligible=p["year_of_study"]>=c["course_level"] or r.random()<.12
            if eligible:
                status=r.choices(["INTERESTED","REGISTERED","WAITLISTED","WITHDRAWN"],[35,50,10,5])[0]
            else:
                status=r.choices(["INTERESTED","WITHDRAWN"],[35,5])[0]
            interests.append(dict(interest_id=f"INT-{len(interests)+1:08d}",student_plan_id=p["student_plan_id"],course_id=c["course_id"],term_id=p["term_id"],interest_status=status,interest_date="2026-10-15",eligible=eligible))
    historical=[]
    for i,c in enumerate(courses,1):
        popularity=15+(i*17%95)+(25 if c["is_elective"] else 0)
        for j,term in enumerate(["2025-FALL","2026-SPRING","2026-FALL"]):
            registrations=max(0,int(popularity*(.88+.08*j)+r.randint(-8,12)))
            enrolled=min(registrations,max(0,int(registrations*r.uniform(.78,.97))))
            historical.append(dict(historical_enrollment_id=f"HEN-{len(historical)+1:08d}",course_id=c["course_id"],term_id=term,eligible_students=max(10,int(scale.student_plans/max(1,scale.programs)*.7)),registrations=registrations,enrolled=enrolled,unmet_demand=registrations-enrolled))
    return {
      "academic_terms":pd.DataFrame([
          dict(term_id=TARGET_TERM_ID,start_date="2027-01-01",end_date="2027-05-31")
      ]),
      "programs":pd.DataFrame(programs),"courses":pd.DataFrame(courses),
      "prerequisites":pd.DataFrame(prereqs,columns=["prerequisite_id","course_id","prerequisite_course_id","effective_from","effective_to"]),
      "faculty":pd.DataFrame(faculty),"faculty_skills":pd.DataFrame(skills),"availability":pd.DataFrame(availability),
      "rooms":pd.DataFrame(rooms),"student_plans":pd.DataFrame(plans),"registration_interests":pd.DataFrame(interests),
      "historical_enrollments":pd.DataFrame(historical)
    }

def make_ground_truth():
    return pd.DataFrame([
      ["ANM-000001","FACULTY_OUTSIDE_SKILL","workload_assignment","WLA-SYNTHETIC-000001","Faculty-course pair missing from skill bridge","REJECT_ASSIGNMENT"],
      ["ANM-000002","WORKLOAD_EXCEEDED","faculty","FAC-000001","Proposed load exceeds weekly limit","REJECT_OR_REASSIGN"],
      ["ANM-000003","SECTION_CAPACITY_TOO_LOW","section","SEC-SYNTHETIC-000001","Forecast demand exceeds available seats","ADD_SECTION_OR_RECORD_UNMET"],
      ["ANM-000004","PREREQUISITE_SEQUENCE_VIOLATION","registration_interest","INT-00000001","Student has not met prerequisite","FLAG_INELIGIBLE"],
      ["ANM-000005","DUPLICATE_SECTION_ASSIGNMENT","workload_assignment","WLA-SYNTHETIC-000002","Duplicate faculty-section pair","REJECT_DUPLICATE"]
    ],columns=["case_id","issue_type","entity_type","entity_id","description","expected_decision"])

def export_dataset(frames,out_dir,seed=20261022,scale=None):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    manifest={
        "seed":seed,
        "scale":asdict(scale or Scale()),
        "tables":{},
    }
    for name,df in frames.items():
        path=out/f"{name}.csv"; df.to_csv(path,index=False); df.to_json(out/f"{name}.json",orient="records",indent=2)
        manifest["tables"][name]={"rows":len(df),"sha256_csv":hashlib.sha256(path.read_bytes()).hexdigest(),"columns":list(df.columns)}
    gt=make_ground_truth(); gt.to_csv(out/"ground_truth.csv",index=False)
    manifest["ground_truth"]={"rows":len(gt),"sha256_csv":hashlib.sha256((out/"ground_truth.csv").read_bytes()).hexdigest()}
    (out/"source_manifest.json").write_text(json.dumps(manifest,indent=2))
    return manifest
