import math
import pandas as pd

def propose_sections(forecasts,rooms,term_id="2027-SPRING"):
    active=rooms[rooms["active"]].sort_values("capacity")
    max_room=int(active["capacity"].max()) if not active.empty else 40
    cap=min(40,max_room); rows=[]; room_slots=set()
    for _,r in forecasts.iterrows():
        n=max(1,math.ceil(int(r.forecast_enrollment)/cap))
        for i in range(1,n+1):
            idx=len(rows)+1
            day=(idx-1)%5; slot=f"S{((idx-1)//5)%4+1}"
            candidates=active[active["capacity"]>=cap]
            room_id=None
            for _,room in candidates.iterrows():
                if (room.room_id,day,slot) not in room_slots:
                    room_id=room.room_id; room_slots.add((room_id,day,slot)); break
            rows.append({"section_id":f"SEC-2027-{idx:06d}","course_id":r.course_id,"term_id":term_id,
                "section_number":i,"room_id":room_id,"day_of_week":day,"slot_id":slot,
                "planned_capacity":cap,"forecast_demand":int(r.forecast_enrollment),
                "status":"PROPOSED" if room_id else "PARTIAL"})
    return pd.DataFrame(rows)

def calculate_unmet(forecasts,sections):
    rows=[]
    for _,f in forecasts.iterrows():
        s=sections[sections.course_id==f.course_id]
        seats=int(s.loc[s.room_id.notna(),"planned_capacity"].sum()) if "room_id" in s.columns else int(s.planned_capacity.sum()) if len(s) else 0
        demand=int(f.forecast_enrollment)
        rows.append({"course_id":f.course_id,"forecast_demand":demand,"accommodated":min(demand,seats),
            "unmet":max(0,demand-seats),"reason":"NO_SECTIONS" if not len(s) else ("ROOM_OR_CAPACITY_LIMIT" if seats<demand else "NONE")})
    return pd.DataFrame(rows)
