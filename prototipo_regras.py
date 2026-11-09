import pandas as pd, sys
pd.set_option('display.width',250); pd.set_option('display.max_columns',30); pd.set_option('display.max_rows',200)
D='./'  # rode a partir da pasta Arvo_Case
s=pd.read_csv(D+'arvo.case/sinistro-hospital-saorafael.csv',dtype=str,encoding='utf-8-sig')
num=lambda x: float(x.replace('.','').replace(',','.'))
s['qtd']=s.qtd.astype(int); s['vu']=s.vl_unitario.map(num); s['vt']=s.vl_total.map(num)
s['vt_calc']=s.qtd*s.vu
print('vt inconsist', (abs(s.vt-s.vt_calc)>0.01).sum())
A1={'31001012':4200,'31309062':3100,'30715016':3800,'10101039':120,'20103077':1250,'20103050':620,'60012010':480,'60023011':1600,'99999001':350,'40304361':18,'40901416':320,'40808157':140,'70520020':45,'70402600':9,'70451938':280,'90070020':16,'90050010':4}
A2={'31001012':'20103077','31309062':'20103050','30715016':'20103077'}
ROT={'70520020','70402600'}
contas=s.groupby('id_conta').cod_tuss.apply(set)
def rules(r):
    hits=[]
    cods=contas[r.id_conta]
    pk=[p for p in A2 if p in cods]
    salas={A2[p] for p in pk}
    if pk and (r.cod_tuss in ROT):
        hits.append(('3.3-material_rotina', r.vt))
    if pk and r.cod_tuss in salas:
        hits.append(('3.3-taxa_sala', r.vt))
    if r.cod_tuss=='99999001' and r.carater_atendimento=='Eletivo':
        hits.append(('4.2-urgencia_eletivo', r.vt))
    p=A1.get(r.cod_tuss)
    if p is not None and r.vu>p+1e-9:
        hits.append(('2.2-preco', round((r.vu-p)*r.qtd,2)))
    return hits
s['hits']=s.apply(rules,axis=1)
s['pred']=s.hits.map(bool)
# valor glosado: regra integral prevalece (nao somar com excedente)
def val(h):
    if not h: return 0
    integ=[v for k,v in h if not k.startswith('2.2')]
    return max(integ) if integ else h[0][1]
s['glosa']=s.hits.map(val)
print('itens glosados',s.pred.sum(),'valor total glosado',round(s.glosa.sum(),2),'sinistro total',round(s.vt.sum(),2))
from collections import Counter
c=Counter(); v=Counter()
for h in s.hits:
    for k,x in h: c[k]+=1
for h,g in zip(s.hits,s.glosa):
    if h: v['+'.join(sorted(k for k,_ in h))]+=g
print(c); print(v)
g=pd.read_csv(D+'arvo.case/gabarito-auditoria.csv',dtype=str,encoding='utf-8-sig')
m=g.merge(s,on=['id_item'],how='left',suffixes=('_g',''))
m['y']=m.indevido=='Sim'
tp=(m.y&m.pred).sum(); fp=(~m.y&m.pred).sum(); fn=(m.y&~m.pred).sum(); tn=(~m.y&~m.pred).sum()
print('gab n',len(m),'pos',m.y.sum(),'TP FP FN TN',tp,fp,fn,tn,'prec',tp/(tp+fp),'rec',tp/(tp+fn))
cols=['id_item','id_conta','cod_tuss','desc_item','carater_atendimento','tipo_conta','qtd','vu','hits','indevido']
print('--- FP'); print(m[~m.y&m.pred][cols].to_string())
print('--- FN'); print(m[m.y&~m.pred][cols].to_string())
