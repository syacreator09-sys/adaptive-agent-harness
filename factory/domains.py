DOMAIN_DEFAULTS={
 "code":{"roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},"evidence":["tests","build","http","browser","diff"]},
 "content":{"roles":{"planner":"content_strategist","builder":"content_producer","fixer":"content_producer","worker":"content_producer","tester":"content_evaluator","evaluator":"content_evaluator"},"evidence":["dimensions","duration","captions","spelling","claims","cta"]},
 "research":{"roles":{"planner":"planner","builder":"researcher","fixer":"researcher","worker":"researcher","tester":"fact_checker","evaluator":"fact_checker"},"evidence":["sources","citations","contradictions","recency"]},
 "operations":{"roles":{"planner":"planner","builder":"builder","fixer":"fixer","worker":"worker","tester":"tester","evaluator":"evaluator"},"evidence":["dry_run","simulation","logs","rollback"]},
}
def get_domain(name:str):
    if name not in DOMAIN_DEFAULTS: raise KeyError(name)
    return DOMAIN_DEFAULTS[name]
def role_for(domain:str,canonical:str)->str: return get_domain(domain)["roles"].get(canonical,canonical)
