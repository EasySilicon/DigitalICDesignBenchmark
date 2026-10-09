#!/usr/bin/env python3
"""Prepare/run one persistent, skill-free Codex T08 pilot in a fresh Docker."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from benchmark.prepare_trial import prepare

NAME="ic-bcmk-gpt61sol-t08-mac-20261007"
MODEL="gpt-6.1-sol"
LIMIT=7200
NODE="/home/reefshark/.nvm/versions/node/v24.15.0"
OSS="/data/zhongzhuanzhan/ic_bcmk_tools/oss-cad-suite"
RG=f"{NODE}/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-path"
TOOL_PATH=f"{RG}:{NODE}/bin:/home/reefshark/.local/bin:{OSS}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def setup(root):
    root.mkdir(parents=True,exist_ok=False)
    work=root/"workspace"
    prepare("T08",work)
    task_meta=yaml.safe_load((work/"benchmark/tasks/T08/task.yaml").read_text())
    with (work/"PROMPT.md").open("a") as out:
        out.write("\nThis is a brownfield task. Modify the supplied rtl/ rather than "
                  "starting over. T08 task.md/acceptance.md override incompatible "
                  "shared ten-task rules. No Agent Skills are available: do not "
                  "search for, load, install or use any skill, plugin or MCP server. "
                  "Web Search is disabled. Do not fetch upstream or this benchmark "
                  "repository. Use local tools and this task's public input only. "
                  "No helpers or parallel model Agents: one candidate session. "
                  "The timer begins at launch; deadline is in TRIAL_CLOCK.json. "
                  "Check your remaining time periodically. Preserve the session.\n")
    for directory in ("codex_home","empty_skills","tmp","telemetry_eda","grading","frozen_judge"):
        (root/directory).mkdir()
    shutil.copy2(Path.home()/".codex/auth.json",root/"codex_home/auth.json")
    (root/"codex_home/auth.json").chmod(0o600)
    install=Path.home()/".codex/installation_id"
    if install.is_file(): shutil.copy2(install,root/"codex_home/installation_id")
    # Freeze judge outside the candidate mount; it is never injected into Docker.
    for relative in ("evaluator/public_check.py","evaluator/public/tb_T08.sv",
                     "evaluator/t08_check.py","evaluator/fixtures/t11_mac/tb_acceptance.sv",
                     "benchmark/eda_time.py"):
        target=root/"frozen_judge"/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
    inventory=[{"path":str(p.relative_to(work)),
                "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes":p.stat().st_size} for p in sorted(work.rglob("*")) if p.is_file()]
    write(root/"starting_inventory.json",inventory)
    if any(work.rglob("SKILL.md")) or any((root/"empty_skills").iterdir()):
        raise RuntimeError("skill contamination")
    subprocess.run(["git","init","-b","main",str(work)],check=True,capture_output=True)
    subprocess.run(["git","-C",str(work),"add","."],check=True)
    subprocess.run(["git","-C",str(work),"-c","user.name=Benchmark Harness",
                    "-c","user.email=benchmark@localhost","commit","-m",
                    "Frozen public buggy T08 starter"],check=True,capture_output=True)
    write(root/"run_manifest.json",{"task":"T08","experimental":True,"model":MODEL,
        "spec_revision":task_meta.get("spec_revision","1.0-pilot"),
        "starter_revision":task_meta.get("starter_revision","1.0-padding-crc"),
        "judge_revision":task_meta.get("judge_revision","1.0-pilot"),
        "reasoning_effort":"high","time_limit_seconds":LIMIT,
        "aggregate_token_cap":None,"token_stop_enabled":False,"session_persistence":True,
        "skills":"disabled; empty read-only mount; no host discovery/plugins/apps",
        "web_search":"disabled","container":NAME,"prepared_utc":utc(),
        "tool_image":"ubuntu:24.04","resource_limits":{"memory_gib":32,"cpus":16},
        "judge_scope":"host only, frozen, not mounted",
        "eda_method":"host /proc sampled at 0.1 seconds, union wall time"})
    write(root/"status.json",{"status":"prepared","model":MODEL,"task":"T08"})
    print(f"Prepared {root}",flush=True)

def command(root, *, session_id=None, seconds=LIMIT, container_name=NAME,
            gate="start_trial"):
    work=root/"workspace"
    cmd=["docker","run","--name",container_name,"--network","host","--user","1000:1000",
         "--cpus","16","--memory","32g","--memory-swap","32g","--pids-limit","4096",
         "--security-opt","no-new-privileges","--read-only"]
    for key in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy",
                "all_proxy","NO_PROXY","no_proxy"):
        cmd+=["-e",key]
    cmd+=["-e","HOME=/home/reefshark","-e","CODEX_HOME=/home/reefshark/.codex",
          "-e",f"PATH={TOOL_PATH}","-e","LANG=C.UTF-8","-e","LC_ALL=C.UTF-8",
          "-e","CCACHE_DIR=/tmp/ccache"]
    for source,target in [
        ("/usr","/usr"),("/bin","/bin"),("/lib","/lib"),("/lib64","/lib64"),
        ("/etc/passwd","/etc/passwd"),("/etc/group","/etc/group"),("/etc/ssl","/etc/ssl"),
        ("/home/reefshark/.nvm","/home/reefshark/.nvm"),
        ("/home/reefshark/.local","/home/reefshark/.local"),(OSS,OSS)]:
        cmd+=["-v",f"{source}:{target}:ro"]
    cmd+=["-v",f"{work}:/workspace",
          "-v",f"{root/'codex_home'}:/home/reefshark/.codex",
          "-v",f"{root/'empty_skills'}:/home/reefshark/.codex/skills:ro",
          "-v",f"{root/'tmp'}:/tmp","-w","/workspace","ubuntu:24.04","bash","-c",
          f"export PATH={TOOL_PATH}; "
          f"while [ ! -f /tmp/{gate} ]; do sleep 0.1; done; "
          f"exec timeout --signal=INT --kill-after=30s {seconds}s codex exec --json "
          "--ignore-user-config --enable skip_host_skill_discovery "
          "--disable skill_search --disable skill_mcp_dependency_install "
          "--disable plugins --disable plugin_sharing --disable apps "
          "--disable remote_plugin --disable recommended_plugins "
          f"-m {MODEL} -c 'model_reasoning_effort=\"high\"' "
          "-c 'web_search=\"disabled\"' --dangerously-bypass-approvals-and-sandbox "
          "-C /workspace --output-last-message /workspace/last_message.txt "
          + (f"resume {shlex.quote(session_id)} - < /workspace/RESUME_PROMPT.md"
             if session_id else "- < /workspace/PROMPT.md")]
    return cmd

def synthesis(root):
    from evaluator.public_check import sources_from_filelist
    sources=sources_from_filelist(root/"workspace")
    script="read_verilog -defer -sv "+" ".join(map(str,sources))+"; "
    script+="hierarchy -check -top mac_1g_repair; proc; opt; check -assert; memory_collect; stat"
    with (root/"grading/yosys.log").open("w") as log:
        result=subprocess.run(["yosys","-Q","-p",script],stdout=log,stderr=subprocess.STDOUT,
                              timeout=300,check=False)
    return {"passed":result.returncode==0,"exit_code":result.returncode,
            "method":"Yosys hierarchy/proc/opt/check/memory_collect; no routed PPA"}

def run(root, resume=False):
    manifest=json.loads((root/"run_manifest.json").read_text())
    state=json.loads((root/"status.json").read_text())
    session_id=None
    prior_elapsed=0
    prior_eda=[]
    container_name=NAME
    gate="start_trial"
    runtime=root
    seconds=LIMIT
    if resume:
        if state["status"] not in {"complete","runner_error"}:
            raise RuntimeError("pilot must be stopped before resume")
        previous=json.loads((root/"summary.json").read_text())
        prior_elapsed=float(previous["elapsed_seconds"])
        prior_eda=previous.get("eda_segments",[previous["eda"]])
        seconds=int(LIMIT-prior_elapsed)
        if seconds<=0: raise RuntimeError("original wall-time budget exhausted")
        session_id=json.loads((root/"session.json").read_text())["thread_id"]
        index=len(manifest.get("resumes",[]))+1
        runtime=root/"resumes"/f"{index:02d}"
        runtime.mkdir(parents=True,exist_ok=False)
        archive=runtime/"before_resume"
        archive.mkdir()
        for filename in ("status.json","summary.json","run_manifest.json",
                         "command.json","token_budget.json"):
            shutil.copy2(root/filename,archive/filename)
        shutil.copytree(root/"grading",archive/"grading")
        shutil.copytree(root/"workspace/rtl",archive/"rtl")
        shutil.copytree(root/"workspace/verif",archive/"verif")
        shutil.copy2(root/"workspace/TRIAL_CLOCK.json",archive/"TRIAL_CLOCK.json")
        container_name=f"{NAME}-resume-{index}"
        gate=f"start_resume_{index}"
        if (root/"tmp"/gate).exists():
            raise RuntimeError("resume gate already exists")
        (root/"workspace/RESUME_PROMPT.md").write_text(
            "Continue the existing T08 session using the current RTL and verification "
            "files. Do not restart from scratch. The previous run was interrupted by "
            "an orchestrator-imposed cumulative-token cap, not a model/service "
            "limit. The user explicitly removed that cap. Token usage is now "
            "recorded only; there is NO token hard limit. "
            f"You have {seconds} seconds remaining of the original 7200-second "
            "budget; the orchestrator interruption is excluded. Read the updated "
            "TRIAL_CLOCK.json and task.md. No Skills, plugins, MCP or web search "
            "are available. Do not access reference RTL, hidden acceptance or "
            "other repositories. No hidden-test results are supplied. Finish your "
            "own verification and fix any failures; deliver executable run.sh, "
            "results.json and README.md under the original task contract. Run.sh "
            "must work without externally provided cache/build environment. "
            "Keep the persistent session and summarize exact results and limitations.\n")
        manifest.setdefault("resumes",[]).append({
            "index":index,"session_id":session_id,"remaining_seconds":seconds,
            "prior_elapsed_seconds":prior_elapsed,"reason":"user_removed_token_cap",
            "container":container_name})
    elif state["status"]!="prepared":
        raise RuntimeError("refusing to restart previously launched pilot")
    manifest.update({"aggregate_token_cap":None,"token_stop_enabled":False,
                     "container":container_name})
    if any((root/"empty_skills").iterdir()) or any((root/"workspace").rglob("SKILL.md")):
        raise RuntimeError("skill contamination")
    cmd=command(root,session_id=session_id,seconds=seconds,
                container_name=container_name,gate=gate)
    write(runtime/"command.json",cmd)
    telemetry=runtime/"telemetry_eda"
    telemetry.mkdir(exist_ok=True)
    edalog=(runtime/"eda_monitor.log").open("w")
    monitor=subprocess.Popen([sys.executable,str(root/"frozen_judge/benchmark/eda_time.py"),
        "--container-prefix",container_name,"--output-dir",str(telemetry),
        "--interval","0.1","--idle-stop-seconds","60"],stdout=edalog,stderr=subprocess.STDOUT)
    process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,bufsize=1)
    stop_watch=threading.Event()
    try:
        # Deliberately gate Agent launch until EDA sampling is attached.
        deadline=time.monotonic()+45
        while not list(telemetry.glob("*/eda_time.json")):
            if process.poll() is not None: raise RuntimeError("container exited before start")
            if time.monotonic()>deadline: raise RuntimeError("EDA monitor did not attach")
            time.sleep(0.1)
        start=time.time()
        clock={"started_utc":utc(),"started_epoch":start,"deadline_epoch":start+seconds,
               "deadline_utc":dt.datetime.fromtimestamp(start+seconds,dt.timezone.utc).isoformat(),
               "time_limit_seconds":LIMIT,"remaining_seconds":seconds,
               "prior_elapsed_seconds":prior_elapsed,"token_stop_enabled":False}
        write(root/"workspace/TRIAL_CLOCK.json",clock)
        write(root/"status.json",{"status":"running","model":MODEL,"task":"T08",**clock})
        manifest.update(clock);write(root/"run_manifest.json",manifest)
        (root/"tmp"/gate).touch()
        print(f"AGENT_START {MODEL} T08 {clock}",flush=True)
        budget_reason=[]
        def usage_watch():
            reported=0
            while not stop_watch.wait(2):
                for session in (root/"codex_home/sessions").rglob("*.jsonl"):
                    try:
                        for line in session.read_text(errors="replace").splitlines():
                            item=json.loads(line)
                            if item.get("type")=="event_msg" and item.get("payload",{}).get("type")=="token_count":
                                usage=item["payload"].get("info",{}).get("total_token_usage",{})
                                reported=max(reported,int(usage.get("total_tokens",0)))
                        write(root/"token_budget.json",{"reported_total_tokens":reported,
                              "cap":None,"stop_enabled":False,"timestamp_utc":utc()})
                    except (OSError,ValueError,TypeError): pass
        threading.Thread(target=usage_watch,daemon=True).start()
        with (runtime/"codex_events.jsonl").open("w") as log, (runtime/"codex_stderr.log").open("w") as errors:
            for line in process.stdout:
                try:
                    event=json.loads(line)
                    log.write(line); log.flush()
                    kind=event.get("type","")
                    item=event.get("item",{})
                    if kind=="thread.started":
                        if session_id and event.get("thread_id")!=session_id:
                            raise RuntimeError("resume changed session identity")
                        write(root/"session.json",event);print(f"SESSION {event}",flush=True)
                    elif kind in {"item.completed","item.started"}:
                        print(f"[{kind}] {item.get('type','')}",flush=True)
                        print(item.get("text",item.get("command",item.get("message",""))),flush=True)
                        if kind=="item.completed" and item.get("aggregated_output"):
                            print(item["aggregated_output"],flush=True)
                    else: print(line,end="",flush=True)
                except ValueError:
                    errors.write(line);errors.flush();print(line,end="",flush=True)
        code=process.wait(); segment_elapsed=time.time()-start
        elapsed=prior_elapsed+segment_elapsed
        stop_watch.set()
        write(root/"status.json",{"status":"grading","agent_exit_code":code,
               "elapsed_seconds":elapsed,"finished_utc":utc(),"stop_reason":budget_reason})
        print(f"AGENT_FINISH exit={code} elapsed={elapsed:.1f}",flush=True)
        # Candidate is stopped before host-only grading begins.
        time.sleep(3)
        monitor.terminate(); monitor.wait(timeout=10)
        sys.path.insert(0,str(root/"frozen_judge"))
        from evaluator.t08_check import evaluate
        report=evaluate(root/"workspace",root/"grading/functional.json")
        try: report["synthesis"]=synthesis(root)
        except Exception as error: report["synthesis"]={"passed":False,"error":str(error)}
        report.update({"model":MODEL,"elapsed_seconds":elapsed,"agent_exit_code":code,
                       "segment_elapsed_seconds":segment_elapsed,
                       "prior_elapsed_seconds":prior_elapsed,
                       "token_stop_enabled":False,
                       "stop_reason":budget_reason,"finished_utc":utc()})
        reports=list(telemetry.glob("*/eda_time.json"))
        if reports:
            report["eda_segments"]=[*prior_eda,json.loads(reports[0].read_text())]
            report["eda"]={
                "method":"host_proc_sampling","sampling_interval_seconds":0.1,
                "finished":True,
                "eda_wall_seconds_estimate":sum(s["eda_wall_seconds_estimate"] for s in report["eda_segments"]),
                "observed_call_count":sum(s["observed_call_count"] for s in report["eda_segments"]),
                "note":"sum of non-overlapping contestant segments; interruption/judge excluded"}
        delivery_files=("run.sh","results.json","README.md")
        report["missing_delivery_files"]=[name for name in delivery_files
                                          if not (root/"workspace"/name).is_file()]
        report["delivery_artifacts_present"]=not report["missing_delivery_files"]
        write(root/"summary.json",report)
        write(root/"status.json",{"status":"complete","functional_total":report["functional_total"],
                                "elapsed_seconds":elapsed,"finished_utc":utc()})
        print(json.dumps(report,indent=2),flush=True)
    except BaseException as error:
        stop_watch.set()
        subprocess.run(["docker","stop","--time","10",container_name],capture_output=True)
        write(root/"status.json",{"status":"runner_error","error":str(error),"utc":utc()})
        raise
    finally:
        if monitor.poll() is None: monitor.terminate();monitor.wait(timeout=10)
        edalog.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--prepare-only",action="store_true")
    parser.add_argument("--resume",action="store_true")
    args=parser.parse_args(); root=args.root.resolve()
    if args.prepare_only: setup(root)
    else: run(root,resume=args.resume)

if __name__=="__main__": main()
