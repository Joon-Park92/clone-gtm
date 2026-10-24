"""Evolving multi-account portfolio demo: fixed synthetic agents, no network or credentials."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import copy
import json
import sys
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from portfolio import (digest, initial_state, admit, set_asset, plan_batch, record_publication,
                       settle, winner_candidate, promote, generation_request, complete_generation)
START = datetime(2026,10,1,tzinfo=timezone.utc)


def fixture_config():
    cfg=json.loads((ROOT/'config/portfolio.json').read_text())
    cfg.update(campaign_id='MOCK-PORTFOLIO',mode='mock_simulation',window={'start':START.isoformat(),'end':(START+timedelta(days=7)).isoformat()})
    cfg['attribution'].update(level='deployment',verified=True)
    cfg['accounts']=[{'account_id':f'mock-account-{i}','public_handle':f'mock_{i}',
       'ownership_confirmed':True,'publishing_verified':True,'active':True,'context_block':'daily'} for i in range(3)]
    return cfg


def fixture_rubrics():
    cfg=json.loads((ROOT/'config/portfolio.json').read_text())
    return {role:json.loads((ROOT/'config'/path).read_text()) for role,path in cfg['rubrics'].items()}


class JsonAgent:
    """Manual/provider bridge; the coordinator still validates returned hashes and evidence."""
    def __init__(self,path): self.path=path
    def run(self,task,rubric,evidence): return json.loads(self.path.read_text())


class MockAgent:
    def __init__(self,role): self.role=role; self.agent_id='mock-'+role
    def run(self,task,rubric,evidence):
        return {'subject_hash':digest(task),'rubric_hash':digest(rubric),'role':self.role,'agent_id':self.agent_id,
           'criteria':{c['id']:{'score':2,'reason':'Synthetic pass fixture, not actual agent quality',
                               'evidence_refs':list(evidence)} for c in rubric['criteria']},
           'gates':{g:{'status':'pass','reason':'Synthetic fixture only','evidence_refs':list(evidence)} for g in rubric['gates']}}


class MockGenerator(MockAgent):
    def __init__(self): super().__init__('hypothesis_generator')
    def propose(self,request,evidence):
        if request is None:
            domains=[('ARM-FOOD','restaurant_availability','seed'),('ARM-DELIVERY','delivery_tracking','seed'),('ARM-CART','shopping_cart','seed')]
        else:
            domains=[('ARM-LOW-CHILD',request['refinement_domain'],'refinement'),('ARM-EMAIL-CHILD','email_summary','expansion')][:request['maximum_candidates']]
        return [{'arm_id':key,'domain':domain,'origin':origin,'parent_arm_id':(request['refinement_parent_arm_id'] if origin=='refinement' else request['expansion_parent_arm_id']) if request else None,
          'audience':'SYNTHETIC: 반복 앱 작업을 확인하는 사람','problem':domain+' 확인을 반복하는 수고',
          'offer':'Mu 사전 사용 신청','prediction':'확인된 신규 사전 신청이 생길 수 있다',
          'falsifier':'반응에 위임 의사 없음·신청 없음이 반복되면 재검토',
          'generator_id':self.agent_id,'changed_axis':'task_domain' if origin=='expansion' else 'request_frequency',
          'evidence_refs':list(evidence)} for key,domain,origin in domains]


def evidence_fixture():
    return {'EV-PRODUCT':{'kind':'synthetic_product','observation':'Mu의 예약·배송·장바구니·메일 소개를 가정한 합성 fixture'},
            'EV-REACTION':{'kind':'synthetic_reaction','observation':'배송 확인 위임과 아침 메일 요약을 원하는 합성 반응; 실제 고객 아님'}}


def add_hypothesis(cfg,state,h,rubrics,evidence):
    gen,rev=MockAgent('hypothesis_generator'),MockAgent('hypothesis_reviewer')
    admit(cfg,state,h,gen.run(h,rubrics[gen.role],evidence),rev.run(h,rubrics[rev.role],evidence),rubrics,evidence)
    body='MOCK ONLY: '+h['problem']+'를 메신저로 부탁한다면? 현재 사전 신청 단계. https://example.invalid/mock-signup'
    writer=MockAgent('content_writer'); subject={'arm_id':h['arm_id'],'body':body}
    set_asset(state,h['arm_id'],body,writer.run(subject,rubrics[writer.role],evidence),rubrics[writer.role],evidence)


def outcome(cfg,dep,at,n):
    deadline=datetime.fromisoformat(dep['posted_at'])+timedelta(hours=cfg['policy']['outcome_hours'])
    return {'deployment_id':dep['deployment_id'],'campaign_id':cfg['campaign_id'],'window_end':deadline.isoformat(),
      'observed_through':at.isoformat(),'verified_receipts':True,'baseline_excluded':True,'campaign_deduplicated':True,
      'complete':True,'credit_ids':[f"CREDIT-{dep['deployment_id']}-{i}" for i in range(n)],'evidence_refs':['EV-MOCK-RECEIPTS']}


def publish(cfg,state,job,at):
    record_publication(cfg,state,job,{'human_reviewed':True,'job_hash':digest(job),'approved_at':at.isoformat()},
      {'deployment_id':job['deployment_id'],'account_id':job['account_id'],'status':'posted',
       'posted_at':at.isoformat(),'url':'https://example.invalid/'+job['deployment_id']})


def run_demo(output):
    assert not output.exists()
    output.mkdir(parents=True)
    cfg,rubrics,evidence=fixture_config(),fixture_rubrics(),evidence_fixture()
    state=initial_state(); generator=MockGenerator()
    for h in generator.propose(None,evidence): add_hypothesis(cfg,state,h,rubrics,evidence)
    rounds=[]
    for day in range(8):
        at=START+timedelta(days=day)
        receipts=[]
        for dep in state['deployments'].values():
            if dep['deployment_id'] in state['outcomes']: continue
            if datetime.fromisoformat(dep['posted_at'])+timedelta(hours=24) > at: continue
            reward=3 if state['arms'][dep['arm_id']]['hypothesis']['domain']=='delivery_tracking' else 0
            receipts.append(outcome(cfg,dep,at,reward))
        settle(cfg,state,receipts,at)
        candidate=winner_candidate(cfg,state)
        event=None; children=[]
        if candidate['status']=='candidate':
            reviewer=MockAgent('learning_reviewer')
            event=promote(cfg,state,candidate,reviewer.run(candidate,rubrics[reviewer.role],evidence),rubrics[reviewer.role],evidence)
        request=generation_request(cfg,state,event)
        if request:
            for h in generator.propose(request,evidence):
                add_hypothesis(cfg,state,h,rubrics,evidence); children.append(h['arm_id'])
            complete_generation(state,request,children)
        batch=plan_batch(cfg,state,at)
        for job in batch['jobs']: publish(cfg,state,job,at)
        row={'day':day,'batch':batch,'winner_decision':candidate,'incumbent':state['incumbent'],
             'generation_request':request,'new_arms':children,'mature_deployments':len(state['outcomes']),
             'synthetic_signups':len(state['used_credit_ids'])}
        rounds.append(row)
        (output/f'day-{day}.json').write_text(json.dumps({'simulation_only':True,'round':row,'state':state},ensure_ascii=False,indent=2)+'\n')
    assert state['incumbent']=='ARM-DELIVERY'
    assert len(state['promotions'])==1 and len(state['generation_completed'])==1
    assert state['arms']['ARM-EMAIL-CHILD']['hypothesis']['parent_arm_id']=='ARM-DELIVERY'
    assert len(state['arms'])==5
    assert 'ARM-EMAIL-CHILD' in state['arms']  # Capacity permits one new hypothesis slot in this final round.
    assert rounds[0]['mature_deployments']==0 and rounds[0]['winner_decision']['winner'] is None
    assert rounds[-1]['batch']['status']=='outside_window'
    assert all(len({j['account_id'] for j in r['batch']['jobs']})==len(r['batch']['jobs']) for r in rounds)
    assert any(j['allocation_reason']=='observed_high' for r in rounds for j in r['batch']['jobs'])
    assert any(j['allocation_reason'] in ('observed_low','low_hypothesis_revision') for r in rounds for j in r['batch']['jobs'])
    report={'simulation_only':True,'result':'PASS','accounts':3,'initial_arms':3,'final_arms':5,
            'incumbent':state['incumbent'],'mature_deployments':len(state['outcomes']),
            'synthetic_signups':len(state['used_credit_ids']),'generation_events':len(state['promotions']),
            'external_calls':0,'real_credentials_read':False,'parallel_plan_only':True}
    for name,value in [('summary.json',report),('config.json',cfg),('rubrics.json',rubrics)]:
        p=output/name; p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n'); assert json.loads(p.read_text())==value
    table='\n'.join(f"| {r['day']} | {len(r['batch']['jobs'])} | {r['mature_deployments']} | {r['incumbent']} | {', '.join(r['new_arms']) or '-'} |" for r in rounds)
    (output/'report.md').write_text('''# 다계정·가설 포트폴리오 Mock

모든 계정·반응·신청·승인·시간은 합성이다. 실제 외부 호출·로그인·게시·모델 추론은 없다. 병렬 배포 슬롯을 계획하고 합성 영수증으로 기록했으며 실제 병렬 네트워크 실행은 검증하지 않았다.

초기 음식 예약·배송 조회·장바구니 3개 가설을 계정 3개의 슬롯에 배분했다. 가설별·계정별 관측 기간이 끝난 신청으로만 높음·낮음을 비교했고 배송 조회가 관측상 상위 가설이었다. 독립 역할의 합성 검토 후 낮은 가설의 개선안과 메일 요약 확장을 생성·검토·기존 성과를 물려받지 않는 새 가설로 편입했다. 새 콘텐츠 역시 별도 합성 사람 승인 뒤 기록했다.

| 가상 일차 | 배포 슬롯 | 성숙 관측 누적 | 운영 승자 | 새 가설 |
| --- | --- | --- | --- | --- |
'''+table+'''

Rubric JSON과 subject/rubric hash를 저장해 어떤 기준으로 평가했는지 남겼다. Mock 에이전트는 고정 점수를 반환하므로 실제 에이전트 품질을 입증하지 않는다. 배분 정책·승자 문턱은 운영 가정이며 승자의 인과 효과·향후 성과를 보장하지 않는다. 세부 관측·배분·가설 계보는 day-*.json에 보존했다.
''')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path); args=parser.parse_args()
    out=args.output or ROOT/'runs/mock'/('PORTFOLIO-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6])
    result=run_demo(out)
    print(json.dumps(dict(result,report=str(out/'report.md')),ensure_ascii=False))
