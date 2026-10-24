"""Grounded multi-field retrieval: explicit evidence, lexical relevance and meaning."""
import re
from nlp import ALIASES, tags, normalize, tokens, query_terms, bm25

def local_intent(query,vocabulary):
    query=normalize(query)
    return sorted({tag for tag in vocabulary if re.search(r"(?<!\w)"+re.escape(tag)+r"(?!\w)",query)} |
                  {target for alias,target in ALIASES.items() if target in vocabulary and re.search(r"(?<!\w)"+re.escape(alias)+r"(?!\w)",query)})

def eligible(me,people,window,excluded,active_only,now):
    accepted=[]
    counts={"self":0,"already_met":0,"different_window":0,"not_checked_in":0}
    for p in people:
        if p["id"]==me["id"]:
            counts["self"]+=1
            continue
        if p["id"] in excluded:
            counts["already_met"]+=1
            continue
        windows=tags(p["window"])
        if (window and "anytime" not in windows and normalize(window) not in windows) or (
            not window and "anytime" not in windows and "anytime" not in tags(me["window"]) and not windows.intersection(tags(me["window"]))):
            counts["different_window"]+=1
            continue
        if active_only and p["until_ts"]<=now:
            counts["not_checked_in"]+=1
            continue
        accepted.append(p)
    return accepted,counts

def search_profiles(me,people,query,encoder=None,offered_only=False):
    query=query.strip() or me["needs"] or me["interests"]
    vocab=set().union(*(tags(p["offers"])|tags(p["interests"]) for p in people)) if people else set()
    direct=local_intent(query,vocab)
    original,expansions=query_terms(query)
    expanded_tokens=tokens(" ".join(expansions))
    documents,references=[],[]
    for p in people:
        for field in ("offers","project","interests"):
            documents.append(p[field]);references.append((p["id"],field))
    lexical=bm25(original,documents)
    expanded=bm25(expanded_tokens,documents)
    semantic=encoder.similarities(query,documents) if encoder and encoder.available else [0.0]*len(documents)
    lookup={(pid,field):(lexical[i],expanded[i],semantic[i]) for i,(pid,field) in enumerate(references)}
    results=[]
    for p in people:
        direct_offers=sorted(set(direct)&tags(p["offers"]))
        reciprocal=sorted(tags(me["offers"])&tags(p["needs"]))
        shared=sorted(tags(me["interests"])&tags(p["interests"]))
        evidence=[];field_scores={}
        for field in ("offers","project","interests"):
            lex,exp,sem=lookup[(p["id"],field)]
            matched=sorted(set(original).intersection(tokens(p[field])))
            related=sorted(set(expanded_tokens).intersection(tokens(p[field])))
            if (matched or related or sem>=0.48) and p[field]:
                evidence.append({"field":field,"text":p[field],"matched_terms":matched,"related_terms":related,
                                 "semantic_similarity":round(sem,3) if sem>=0.48 else None})
            field_scores[field]=lex+0.55*exp+max(0,sem-0.3)*4
        if not evidence:
            continue
        if direct and not direct_offers and not set(direct).intersection(tags(p["interests"])) and not any(e["matched_terms"] or e["related_terms"] for e in evidence):
            continue
        offers_evidence=next((e for e in evidence if e["field"]=="offers"),None)
        project_evidence=next((e for e in evidence if e["field"]=="project"),None)
        if offered_only and not offers_evidence:
            continue
        label="Offers relevant skills" if direct_offers else "Related offered skills" if offers_evidence else "Relevant project" if project_evidence else "Shared-interest connection"
        score=5*len(direct_offers)+3*len(reciprocal)+min(len(shared),2)+2*field_scores["offers"]+2.5*field_scores["project"]+field_scores["interests"]
        source=offers_evidence or project_evidence or evidence[0]
        reason=f"{source['field'].title()}: {source['text']}"
        caveat="Self-reported skills; ask about their experience." if offers_evidence else "A relevant project or interest is a conversation lead, not verified expertise."
        if label=="Shared-interest connection":
            starter=f"Hi {p['name']}, I noticed your interest in {p['interests']}. Would you like to compare notes on {query[:150]}?"
        elif project_evidence:
            starter=f"Hi {p['name']}, I saw your project: {p['project']}. Could we discuss {query[:150]}?"
        else:
            starter=f"Hi {p['name']}, you listed {p['offers']}. Could we discuss {query[:150]}?"
        if reciprocal:
            starter+=f" I can also help with {', '.join(reciprocal)}."
        results.append({"id":p["id"],"name":p["name"],"project":p["project"],"offers":p["offers"],"needs":p["needs"],
                        "interests":p["interests"],"window":p["window"],"helps_you":direct_offers,"you_help":reciprocal,"shared":shared,
                        "score":round(score,3),"starter":starter,"label":label,"reason":reason,"caveat":caveat,"evidence":evidence})
    return sorted(results,key=lambda p:(-p["score"],p["id"])),direct,expansions

def attach_presence(results,people,now):
    by_id={p["id"]:p for p in people}
    for item in results:
        p=by_id[item["id"]];active=p["until_ts"]>now
        item.update({"spot":p["spot"] if active else None,"until_ts":p["until_ts"] if active else None,"checked_at":p["checked_at"] if active else None})
    return results
