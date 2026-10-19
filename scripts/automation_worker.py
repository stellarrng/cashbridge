"""Local/cloud single worker. Use cron/systemd or orchestrator; production needs a real queue.

Run: python -m scripts.automation_worker --once
"""
import argparse
import os
import time
from automation.engine import AutomationStore


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--interval',type=int,default=30)
    args=parser.parse_args()
    if args.interval<5: parser.error('Minimum interval is five seconds')
    db=os.environ.get('CASHBRIDGE_AUTOMATION_DB','data/automation_jobs.sqlite3')
    store=AutomationStore(db)
    while True:
        output=store.run_pending(20)
        for job in output:
            print(job['id'],job['kind'],job['state'],flush=True)
        if args.once: break
        time.sleep(args.interval)

if __name__=='__main__': main()
