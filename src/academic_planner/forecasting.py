import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

def forecast_demand(history):
    history=history.copy()
    season_order={"SPRING":0,"SUMMER":1,"FALL":2,"WINTER":3}
    def term_key(term):
        parts=str(term).split("-")
        year=int(parts[0]) if parts and parts[0].isdigit() else 0
        season=season_order.get(parts[1].upper(),9) if len(parts)>1 else 9
        return year*10+season
    history=history.copy()
    history["_term_order"]=history.term_id.map(term_key)
    history=history.sort_values("_term_order")
    terms=list(dict.fromkeys(history.term_id.tolist()))
    if len(terms)<2: raise ValueError("At least two historical terms are required")
    train_rows=[]; test_rows=[]
    for _,g in history.sort_values("_term_order").groupby("course_id"):
        g=g.sort_values("_term_order")
        for i in range(1,len(g)):
            row={"last_enrollment":float(g.enrolled.iloc[i-1]),"registrations":float(g.registrations.iloc[i-1]),"unmet":float(g.unmet_demand.iloc[i-1]),"target":float(g.enrolled.iloc[i])}
            (test_rows if g.term_id.iloc[i]==terms[-1] else train_rows).append(row)
    train=pd.DataFrame(train_rows); test=pd.DataFrame(test_rows)
    features=["last_enrollment","registrations","unmet"]
    model=RandomForestRegressor(n_estimators=80,random_state=20261022,min_samples_leaf=2)
    model.fit(train[features],train.target)
    pred=np.maximum(0,model.predict(test[features]))
    mae=float(mean_absolute_error(test.target,pred)); rmse=float(np.sqrt(mean_squared_error(test.target,pred)))
    baseline_mae=float(mean_absolute_error(test.target,test.last_enrollment))
    latest=[]
    for cid,g in history.sort_values("_term_order").groupby("course_id"):
        row=g.iloc[-1]
        latest.append({"course_id":cid,"last_enrollment":float(row.enrolled),"registrations":float(row.registrations),"unmet":float(row.unmet_demand)})
    last=pd.DataFrame(latest)
    forecast=np.maximum(0,np.rint(model.predict(last[features])).astype(int))
    out=pd.DataFrame({"course_id":last.course_id,"forecast_enrollment":forecast,"baseline_forecast":np.rint(last.last_enrollment).astype(int),"model_name":"RandomForestRegressor"})
    return out,{"evaluation_term":terms[-1],"mae":mae,"rmse":rmse,"baseline_mae":baseline_mae,"courses_forecasted":len(out)}
