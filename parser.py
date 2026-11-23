import re,json,unicodedata
VERSION='1.1.0'
def clean(s):return unicodedata.normalize('NFKC',str(s or '')).strip()
def atom(s):
 s=clean(s).strip('`* \n\t[](){}<>。.')
 if re.fullmatch(r'(?:TRUE|FALSE|正确|错误|对|错|T)',s,re.I):return {'T':'TRUE','正确':'TRUE','错误':'FALSE','对':'TRUE','错':'FALSE'}.get(s.upper(),s.upper())
 if re.fullmatch(r'[A-Ja-j](?:\s*(?:[,，、;；|+/&]|\band\b|和|及|与)?\s*[A-Ja-j])*',s):return '|'.join(sorted(set(re.findall('[A-J]',re.sub(r'\band\b','',s,flags=re.I).upper()))))
 return None
def leading(s):
 s=clean(s).lstrip('*` :：').strip()
 s=re.sub(r'^(?:(?:the\s+)?(?:correct\s+)?(?:answer|option|choice)(?:s)?\s*(?:is|are)?\s*[:：]?\s*)','',s,flags=re.I)
 s=s.lstrip('*` :：')
 s=re.sub(r'^(?:选项|option(?:s)?|choice(?:s)?)\s*','',s,flags=re.I)
 s=re.sub(r'\(([A-J])\)',r'\1',s)
 if re.match(r'^[A-J]\s*(?:or|或|或者)\s*[A-J](?![a-zA-Z])',s):return 'AMBIGUOUS'
 m=re.match(r'^[\[({]?\s*([A-J](?:(?:\s*[,，、;；|+/&]\s*|\s+and\s+|\s*[和及与]\s*|\s+)[A-J](?![a-z])|[A-J])*)\s*[\])}]?(?![a-zA-Z])',s)
 if m:return atom(m.group(1))
 m=re.match(r'^(True|False|正确|错误)(?![a-zA-Z])',s,re.I)
 return atom(m.group(1)) if m else None
def extract(raw,allowed,qtype,options):
 s=clean(raw)
 if not s or s.lower() in {'nan','none','null'}:return '', 'EMPTY_RESPONSE','empty'
 if re.match(r'^(?:error\b|api[_ ]?error|request failed|exception\b|错误[:：]|请求失败|调用失败|429\b|500\b|502\b|503\b|504\b)',s,re.I) or re.search(r'(?:RateLimitError|ConnectionError|APITimeoutError|Error code:\s*\d{3}|insufficient_quota)',s,re.I):return '', 'API_ERROR','api_error'
 if re.match(r'^(?:sorry[,! ]*I (?:didn.t understand|cannot|can.t|am unable)|I (?:cannot|can.t|am unable to) (?:answer|provide|assist)|抱歉|对不起|无法回答)',s,re.I):return '', 'REFUSAL','refusal'
 pred=None;rule=''
 if s.startswith(('{','[')):
  try:
   obj=json.loads(s)
   if isinstance(obj,dict):
    for k in ['final_answer','answer','choice','selected_option']:
     if k in obj:
      v=obj[k];pred=atom(','.join(map(str,v)) if isinstance(v,list) else v);rule='structured:'+k;break
    if pred is None:
     content=obj.get('choices',[{}])[0].get('message',{}).get('content') if 'choices' in obj else obj.get('content')
     if isinstance(content,str):return extract(content,allowed,qtype,options)
  except (ValueError,TypeError,IndexError,AttributeError):pass
 if pred is None:
  # Closed reasoning blocks are excluded; an unclosed block has no final answer.
  if '</think>' in s:s=s.rsplit('</think>',1)[1].strip()
  elif s.startswith('<think>'):return '', 'UNPARSEABLE','unclosed_think'
  s=s.replace('**','').replace('`','').replace('$','')
  s=re.sub(r'\$?\\boxed\{([^{}]+)\}\$?',r'\1',s)
  markers=list(re.finditer(r'(?:final\s+answer|(?:the\s+)?correct\s+(?:answer|option|choice)|answer|select\s+(?:the\s+)?options?)\s*(?:is|are)?\s*[:：]?\s*|(?:最终答案|正确答案|答案)\s*(?:是|为)?\s*[:：]?\s*|(?:我选择|选择)\s*[:：]?\s*',s,re.I))
  for m in reversed(markers):
   v=leading(s[m.end():])
   if v:pred=v;rule='explicit_final';break
  if pred is None:
   lines=[l.strip() for l in s.splitlines() if l.strip()]
   if lines:
    pred=atom(lines[-1]);rule='last_line_direct'
   if pred is None and lines:
    last=lines[-1]
    option_lines=sum(bool(re.match(r'^(?:选项\s*|Option\s*)?[A-J]\s*[:.、]',l)) for l in lines)
    starts_choice=bool(re.match(r'^(?:选项\s*|[Oo]ption\s*)?[\[(]?[A-J](?![a-z])',last))
    if len(last)<300 and option_lines<2 and starts_choice:
     pred=leading(last);rule='last_line_choice'
   if pred is None:
    selections=list(re.finditer(r'(?:options?\s+|选项\s*)((?:\(?[A-J]\)?\s*(?:,|and|、|和)?\s*)+)\s*(?:are|is)\s+(?:correct|the\s+correct)',s))
    if selections:pred=atom(re.sub(r'[()]','',selections[-1].group(1)));rule='explicit_selected_options'
   if pred is None:
    conclusions=list(re.finditer(r'(?:therefore|thus|hence|so[, ]+|would be|is option|所以|因此|故选)[^\n]{0,180}',s,re.I))
    if conclusions:
     tail=conclusions[-1].group(0)
     m=re.search(r'(?:option|choice|answer|选项|选择|选)\s*(?:is|are)?\s*[:：]?\s*([A-J](?![a-zA-Z]))',tail,re.I)
     if m:pred=atom(m.group(1));rule='conclusion'
   if pred is None and len(s)<200:
    matched=[c for c,v in options.items() if clean(v).casefold().strip(' .。')==s.casefold().strip(' .。')]
    if len(matched)==1:pred=matched[0];rule='exact_option_text'
 if pred is None:return '', 'UNPARSEABLE','no_reliable_final'
 if pred=='F' and ('F' not in allowed or qtype=='TF'):pred='FALSE'
 if pred in ['TRUE','FALSE'] and qtype!='TF':
  labels=[c for c,v in options.items() if atom(v)==pred]
  if len(labels)==1:pred=labels[0]
  else:return pred,'INVALID_FORMAT',rule
 if qtype=='TF':valid=pred in ['TRUE','FALSE']
 else:valid=set(pred.split('|'))<=set(allowed) and (qtype=='MULTI' or len(pred.split('|'))==1)
 return pred, 'PARSED' if valid else 'INVALID_FORMAT',rule
