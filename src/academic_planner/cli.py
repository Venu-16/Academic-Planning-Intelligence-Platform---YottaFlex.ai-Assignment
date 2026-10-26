import argparse,json
from .pipeline import run_pipeline
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",default="data/generated"); p.add_argument("--database-url",default=None); p.add_argument("--seed",type=int,default=20261022); p.add_argument("--no-db",action="store_true")
    a=p.parse_args(); print(json.dumps(run_pipeline(a.output_dir,a.database_url,a.seed,not a.no_db),indent=2))
if __name__=="__main__": main()
