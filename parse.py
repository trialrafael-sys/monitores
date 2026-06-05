#!/usr/bin/env python3
"""
parse.py - Serasa Monitore TXT → data.json compacto
Uso: python parse.py arquivo1.txt arquivo2.txt ...
     python parse.py pasta/  (processa todos os .TXT de uma pasta)
     python parse.py --export  (gera data.json + historico_YYYYMMDD.json)

O data.json resultante é ~250KB para ~100 CNPJs / 10 dias.
Os arquivos .TXT originais podem ser descartados após o parse.
"""

import sys, os, json, glob
from datetime import date as dtdate

MONTHS = {'JAN':'01','FEV':'02','MAR':'03','ABR':'04','MAI':'05','JUN':'06',
          'JUL':'07','AGO':'08','SET':'09','OUT':'10','NOV':'11','DEZ':'12'}

def parse_mdate(s):
    s = s.strip()
    if len(s) >= 7 and s[:3].upper() in MONTHS:
        return MONTHS[s[:3].upper()] + '/20' + s[5:7]
    return s

def classify_pend(tipo):
    t = tipo.upper()
    if 'PROTESTO' in t: return 'PROTESTO'
    if 'DIVIDA VENCIDA' in t: return 'DIVIDA_VENCIDA'
    if 'ACAO JUDICIAL' in t: return 'ACAO_JUDICIAL'
    if 'FALEN' in t or 'FALENCIA' in t: return 'FALENCIA'
    if 'RECUP' in t: return 'RECUPERACAO'
    if 'CHEQUE' in t: return 'CHEQUE'
    return 'OUTROS'

def fname_to_date(path):
    """Extrai data do nome do arquivo: R.085.K9881.MONITORE.RET.D260523.H034213.TXT → 2026-05-23"""
    name = os.path.basename(path)
    import re
    m = re.search(r'D(\d{2})(\d{2})(\d{2})', name)
    if m:
        return f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
    return dtdate.today().isoformat()

def parse_file(path):
    """Parseia um arquivo TXT e retorna {cnpj: snap}"""
    date = fname_to_date(path)
    day_data = {}

    with open(path, encoding='latin-1', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n\r')
            if len(line) < 35: continue
            cnpj = line[20:28]
            if not cnpj.isdigit(): continue
            seg = line[28:34]

            if cnpj not in day_data:
                day_data[cnpj] = {
                    'razao': '', 'score': None,
                    'pend': [], 'pefin': [], 'refin': [], 'falrj': [],
                    'nada_geral': False, 'nada_pefin': False, 'nada_refin': False,
                }

            d = day_data[cnpj]

            if seg == '010102':
                r = line[34:114].strip()
                if r and not d['razao']: d['razao'] = r[:60]

            elif seg == '571001':
                try: d['score'] = int(line[34:49][6:9])
                except: pass

            elif seg == '041099' and 'NADA CONSTA' in line:
                d['nada_geral'] = True
            elif seg == '040199' and 'NADA CONSTA' in line:
                d['nada_pefin'] = True
            elif seg == '040299' and 'NADA CONSTA' in line:
                d['nada_refin'] = True

            elif seg == '040202':  # Pendências gerais
                tipo = line[43:70].strip()
                try: val = int(line[87:100].strip())
                except: val = 0
                d['pend'].append({
                    'tipo': tipo, 'cat': classify_pend(tipo),
                    'ini': parse_mdate(line[70:77]),
                    'ult': parse_mdate(line[77:84]),
                    'val': val,
                    'cred': line[100:122].strip(),
                })

            elif seg == '040101':  # PEFIN
                tipo_doc = line[60:73].strip()
                credor = line[76:110].strip()
                d['pefin'].append({'tipo': tipo_doc or 'PEFIN', 'cred': credor})

            elif seg == '040102':  # REFIN
                tipo_doc = line[60:73].strip()
                credor = line[76:110].strip()
                d['refin'].append({'tipo': tipo_doc or 'REFIN', 'cred': credor})

            elif seg == '040601':  # Falência/Recuperação Judicial
                d['falrj'].append({
                    'tipo': line[51:72].strip(),
                    'cidade': line[80:110].strip(),
                    'data': line[43:51].strip(),
                })

    return date, day_data

def build_snapshot_entry(snap):
    """Comprime snapshot para formato compacto."""
    cats = {}
    for p in snap['pend']:
        cat = p['cat']
        if cat not in cats:
            cats[cat] = {'n': 0, 'v': 0, 'items': []}
        cats[cat]['n'] += 1
        cats[cat]['v'] += p['val']
        cats[cat]['items'].append({
            't': p['tipo'], 'i': p['ini'], 'u': p['ult'],
            'v': p['val'], 'c': p['cred']
        })
    return {
        's': snap['score'],
        'nc': snap['nada_geral'],
        'np': snap['nada_pefin'],
        'nr': snap['nada_refin'],
        'cats': cats,
        'pefin': snap['pefin'][:5],
        'refin': snap['refin'][:5],
        'falrj': snap['falrj'][:3],
        'tp': len(snap['pend']),
        'tpf': len(snap['pefin']),
        'trf': len(snap['refin']),
        'tfr': len(snap['falrj']),
    }

def detect_changes(prev, curr, prev_d, curr_d):
    """Detecta mudanças entre dois snapshots consecutivos."""
    prev_cats = set(prev['cats'].keys())
    curr_cats = set(curr['cats'].keys())
    new_cats = list(curr_cats - prev_cats)
    rem_cats = list(prev_cats - curr_cats)

    pefin_delta = curr['tpf'] - prev['tpf']
    refin_delta = curr['trf'] - prev['trf']
    falrj_delta = curr['tfr'] - prev['tfr']

    score_delta = None
    if prev['s'] is not None and curr['s'] is not None and prev['s'] != curr['s']:
        score_delta = curr['s'] - prev['s']

    # LIMINAR: estava limpo (nada consta), entrou algo novo
    was_clean = prev['nc'] and prev['tp'] == 0 and prev['tpf'] == 0
    now_dirty = curr['tp'] > 0 or curr['tpf'] > 0
    liminar = was_clean and now_dirty

    # MAIS ATENÇÃO
    mais_atencao = []
    if pefin_delta > 0 and prev['tpf'] == 0: mais_atencao.append('PEFIN_NOVO')
    elif pefin_delta > 0: mais_atencao.append('PEFIN_AUMENTO')
    if refin_delta > 0 and prev['trf'] == 0: mais_atencao.append('REFIN_NOVO')
    elif refin_delta > 0: mais_atencao.append('REFIN_AUMENTO')
    if falrj_delta > 0: mais_atencao.append('FALRJ_NOVO')
    if liminar: mais_atencao.append('LIMINAR')

    if not (new_cats or rem_cats or pefin_delta or refin_delta or falrj_delta or score_delta or liminar):
        return None

    # Itens novos/removidos
    new_items, rem_items = [], []
    for cat in new_cats:
        for item in curr['cats'][cat]['items'][:3]:
            new_items.append({**item, 'cat': cat})
    for cat in rem_cats:
        for item in prev['cats'][cat]['items'][:3]:
            rem_items.append({**item, 'cat': cat})
    if pefin_delta > 0:
        new_items += [{**p, 'cat': 'PEFIN'} for p in curr['pefin'][:3]]
    elif pefin_delta < 0:
        rem_items += [{**p, 'cat': 'PEFIN'} for p in prev['pefin'][:3]]

    return {
        'f': prev_d, 't': curr_d,
        'nc': new_cats, 'rc': rem_cats,
        'pfd': pefin_delta, 'rfd': refin_delta, 'frd': falrj_delta,
        'sd': score_delta, 'lim': liminar, 'ma': mais_atencao,
        'ni': new_items[:5], 'ri': rem_items[:5],
    }

def merge_into(all_data, cnpj_razao, date, day_data):
    """Mergeia dados de um dia no all_data."""
    for cnpj, snap in day_data.items():
        if cnpj not in all_data:
            all_data[cnpj] = {}
        if date in all_data[cnpj]:
            ex = all_data[cnpj][date]
            if snap['razao'] and not ex.get('razao_raw'):
                ex['razao_raw'] = snap['razao']
            if snap['score'] is not None:
                ex['score'] = snap['score']
            ex['pend'].extend(snap['pend'])
            ex['pefin'].extend(snap['pefin'])
            ex['refin'].extend(snap['refin'])
            ex['falrj'].extend(snap['falrj'])
            if snap['nada_geral']: ex['nada_geral'] = True
            if snap['nada_pefin']: ex['nada_pefin'] = True
            if snap['nada_refin']: ex['nada_refin'] = True
        else:
            all_data[cnpj][date] = snap
        if snap['razao']:
            cnpj_razao[cnpj] = snap['razao']

def build_output(all_data, cnpj_razao):
    """Constrói o JSON final."""
    result = {}
    for cnpj, dates in all_data.items():
        sorted_dates = sorted(dates.keys())
        timeline = {}
        changes = []

        for i, d in enumerate(sorted_dates):
            entry = build_snapshot_entry(dates[d])
            timeline[d] = entry

            if i > 0:
                prev_d = sorted_dates[i-1]
                ch = detect_changes(timeline[prev_d], entry, prev_d, d)
                if ch:
                    changes.append(ch)

        result[cnpj] = {
            'r': cnpj_razao.get(cnpj, cnpj)[:50].strip(),
            'tl': timeline,
            'ch': changes
        }

    all_dates = sorted(set(d for cd in result.values() for d in cd['tl']))
    return {'dates': all_dates, 'cnpjs': result}

def main():
    args = sys.argv[1:]
    export_mode = '--export' in args
    args = [a for a in args if a != '--export']

    if not args:
        print("Uso: python parse.py arquivo1.txt arquivo2.txt ...")
        print("     python parse.py pasta/")
        print("     python parse.py *.txt --export")
        sys.exit(1)

    # Coleta arquivos
    files = []
    for a in args:
        if os.path.isdir(a):
            files += sorted(glob.glob(os.path.join(a, '*.TXT')) +
                           glob.glob(os.path.join(a, '*.txt')))
        elif '*' in a:
            files += sorted(glob.glob(a))
        else:
            files.append(a)

    files = list(dict.fromkeys(files))  # deduplica preservando ordem
    if not files:
        print("Nenhum arquivo .TXT encontrado.")
        sys.exit(1)

    # Carrega data.json existente se houver
    all_data = {}
    cnpj_razao = {}
    existing_dates = []

    if os.path.exists('data.json'):
        print("Carregando data.json existente...")
        with open('data.json', encoding='utf-8') as f:
            old = json.load(f)
        existing_dates = old.get('dates', [])
        for cnpj, cd in old.get('cnpjs', {}).items():
            cnpj_razao[cnpj] = cd.get('r', cnpj)
            all_data[cnpj] = {}
            for d, entry in cd.get('tl', {}).items():
                # Reconstruct raw snap from compact entry
                pend = []
                for cat, cdata in entry.get('cats', {}).items():
                    for item in cdata.get('items', []):
                        pend.append({
                            'tipo': item.get('t',''),
                            'cat': cat,
                            'ini': item.get('i',''),
                            'ult': item.get('u',''),
                            'val': item.get('v',0),
                            'cred': item.get('c',''),
                        })
                all_data[cnpj][d] = {
                    'razao': cnpj_razao[cnpj],
                    'score': entry.get('s'),
                    'pend': pend,
                    'pefin': entry.get('pefin', []),
                    'refin': entry.get('refin', []),
                    'falrj': entry.get('falrj', []),
                    'nada_geral': entry.get('nc', False),
                    'nada_pefin': entry.get('np', False),
                    'nada_refin': entry.get('nr', False),
                }
        print(f"  {len(all_data)} CNPJs, {len(existing_dates)} datas existentes")

    # Processa novos arquivos
    new_dates = []
    for fpath in files:
        date, day_data = parse_file(fpath)
        if date not in existing_dates:
            print(f"  Processando {os.path.basename(fpath)} → {date} ({len(day_data)} CNPJs)")
            merge_into(all_data, cnpj_razao, date, day_data)
            if date not in new_dates:
                new_dates.append(date)
        else:
            print(f"  Pulando {os.path.basename(fpath)} (data {date} já existe)")

    if not new_dates:
        print("Nenhuma data nova encontrada. data.json não foi alterado.")
        return

    # Constrói output
    output = build_output(all_data, cnpj_razao)

    # Salva data.json
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    sz = os.path.getsize('data.json')
    print(f"\ndata.json atualizado: {sz/1024:.0f} KB, {len(output['cnpjs'])} CNPJs, {len(output['dates'])} datas")

    # Exporta histórico comprimido se --export
    if export_mode:
        hist_name = f"historico_{dtdate.today().strftime('%Y%m%d')}.json"
        # Histórico contém apenas o resumo de mudanças (bem menor)
        hist = {'gerado': dtdate.today().isoformat(), 'cnpjs': {}}
        for cnpj, cd in output['cnpjs'].items():
            if cd['ch']:
                hist['cnpjs'][cnpj] = {'r': cd['r'], 'ch': cd['ch']}
        with open(hist_name, 'w', encoding='utf-8') as f:
            json.dump(hist, f, ensure_ascii=False, separators=(',', ':'))
        hz = os.path.getsize(hist_name)
        print(f"{hist_name} criado: {hz/1024:.0f} KB (apenas mudanças)")

    print("Feito.")

if __name__ == '__main__':
    main()
