DOMAIN_DEFAULTS={
 "code":{
   "roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},
   "evidence":["tests","build","http","browser","diff"],
   "gates":{"pro_test":["technical_test","test","tests","build"],"factory_system":["system_test","technical_test","test"]},
 },
 "content":{
   "roles":{"planner":"content_strategist","builder":"content_producer","fixer":"content_producer","worker":"content_producer","tester":"content_evaluator","evaluator":"content_evaluator"},
   "evidence":["dimensions","duration","captions","spelling","claims","cta"],
   "gates":{"pro_test":["content_check"],"factory_system":["content_check"]},
 },
 "research":{
   "roles":{"planner":"planner","builder":"researcher","fixer":"researcher","worker":"researcher","tester":"fact_checker","evaluator":"fact_checker"},
   "evidence":["sources","citations","contradictions","recency"],
   "gates":{"pro_test":["fact_check"],"factory_system":["fact_check"]},
 },
 "operations":{
   "roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},
   "evidence":["dry_run","simulation","logs","rollback"],
   "gates":{"pro_test":["technical_test","dry_run","simulation"],"factory_system":["system_test","dry_run","simulation"]},
 },
}

def get_domain(name:str):
    if name not in DOMAIN_DEFAULTS: raise KeyError(name)
    return DOMAIN_DEFAULTS[name]

def role_for(domain:str, canonical:str)->str:
    return get_domain(domain)["roles"].get(canonical,canonical)

def gate_types(domain:str, gate:str)->set[str]:
    return set(get_domain(domain).get("gates",{}).get(gate,[]))
