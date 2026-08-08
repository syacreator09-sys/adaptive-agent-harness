DOMAIN_DEFAULTS={
 "code":{
   "roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},
   "evidence":["tests","build","http","browser","diff"],
   "pro_test_types":["technical_test"],
   "factory_system_types":["system_test"],
 },
 "content":{
   "roles":{"planner":"content_strategist","builder":"content_producer","fixer":"content_producer","worker":"content_producer","tester":"content_evaluator","evaluator":"content_evaluator"},
   "evidence":["dimensions","duration","captions","spelling","claims","cta"],
   "pro_test_types":["content_check"],
   "factory_system_types":["content_check"],
 },
 "research":{
   "roles":{"planner":"planner","builder":"researcher","fixer":"researcher","worker":"researcher","tester":"fact_checker","evaluator":"fact_checker"},
   "evidence":["sources","citations","contradictions","recency"],
   "pro_test_types":["fact_check"],
   "factory_system_types":["fact_check"],
 },
 "operations":{
   "roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},
   "evidence":["dry_run","simulation","logs","rollback"],
   "pro_test_types":["technical_test"],
   "factory_system_types":["system_test"],
 },
}


def get_domain(name:str):
    if name not in DOMAIN_DEFAULTS:
        raise KeyError(name)
    return DOMAIN_DEFAULTS[name]


def role_for(domain:str, canonical:str)->str:
    return get_domain(domain)["roles"].get(canonical,canonical)


def gate_types(domain:str, stage:str)->set[str]:
    key={"pro_test":"pro_test_types","factory_system":"factory_system_types"}.get(stage)
    if not key:
        raise KeyError(stage)
    return set(get_domain(domain).get(key) or [])
