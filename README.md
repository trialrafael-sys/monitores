# Serasa Monitore — Dashboard

Dashboard de monitoramento de CNPJ via Serasa Monitore, rodando como GitHub Pages estático.

## Como funciona

```
arquivo .TXT (4MB/dia)
       ↓ python parse.py
data.json (~250KB, compacto)
       ↓ GitHub Pages / index.html
Dashboard no browser
```

Os arquivos `.TXT` originais **podem ser descartados** após o parse.  
O `data.json` acumula histórico de forma incremental.

---

## Setup inicial (uma vez)

### 1. Fork / crie o repositório

1. Crie um repositório no GitHub (ex: `serasa-monitore`)
2. Faça upload de todos os arquivos desta pasta:
   - `index.html`
   - `data.json`
   - `parse.py`
   - `README.md`

### 2. Ative o GitHub Pages

- Vá em **Settings → Pages**
- Source: **Deploy from a branch → main → / (root)**
- Salva. Em ~1 minuto o dashboard estará em:  
  `https://SEU_USUARIO.github.io/serasa-monitore/`

---

## Uso diário

### Quando receber um novo arquivo .TXT do Serasa:

```bash
# Na pasta do projeto:
python parse.py R.085.K9881.MONITORE.RET.D260605.H034213.TXT

# Com múltiplos arquivos:
python parse.py *.TXT

# Processar uma pasta inteira:
python parse.py /downloads/serasa/

# Gerar também arquivo de histórico compacto (só mudanças):
python parse.py novo_arquivo.TXT --export
```

O script atualiza o `data.json` automaticamente.  
Arquivos de datas já existentes são ignorados (idempotente).

### Depois do parse:

```bash
git add data.json
git commit -m "Add data $(date +%Y-%m-%d)"
git push
```

Em ~30 segundos o GitHub Pages atualiza.

---

## Uso via browser (sem Python)

O dashboard tem um botão **⊕ CARREGAR .TXT** que:
1. Lê o arquivo direto no browser (sem servidor)
2. Parseia e mergeia os dados
3. Atualiza o dashboard em tempo real
4. Oferece download do novo `data.json` para commit manual

---

## Filtros disponíveis

| Filtro | O que mostra |
|--------|--------------|
| TODOS | Todos os CNPJs |
| PEFIN | CNPJs com Pendência Financeira |
| REFIN | CNPJs com Refinanciamento |
| PROT | CNPJs com Protesto |
| AÇÃO JUD | CNPJs com Ação Judicial |
| FALÊNC | CNPJs com Falência ou Recuperação Judicial |
| ⚠ MAIS ATENÇÃO | PEFIN/REFIN novos + Falência/RJ entrando pela primeira vez |
| ◈ LIMINAR | Empresa estava sem restrições → entrou novo registro |
| COM MUDANÇA | Qualquer alteração detectada entre datas |

---

## Exportar histórico compacto

```bash
python parse.py --export
```

Gera `historico_YYYYMMDD.json` com apenas as mudanças detectadas  
(muito menor que o `data.json` completo). Ideal para arquivamento.

---

## Estrutura do data.json

```json
{
  "dates": ["2026-05-23", "2026-05-26", ...],
  "cnpjs": {
    "00637093": {
      "r": "ALCA FOODS LTDA",
      "tl": {
        "2026-05-23": {
          "s": 102,          // score Serasa
          "nc": true,        // nada consta geral
          "np": false,       // nada consta PEFIN
          "nr": false,       // nada consta REFIN
          "cats": { ... },   // pendências por categoria
          "pefin": [ ... ],  // itens PEFIN
          "refin": [ ... ],  // itens REFIN
          "falrj": [ ... ],  // falência/RJ
          "tp": 3,           // total pendências gerais
          "tpf": 5,          // total PEFIN
          "trf": 2,          // total REFIN
          "tfr": 0           // total falência/RJ
        }
      },
      "ch": [                // mudanças detectadas
        {
          "f": "2026-05-23", // de
          "t": "2026-05-26", // para
          "nc": ["PEFIN"],   // novas categorias
          "rc": [],          // categorias removidas
          "pfd": 3,          // delta PEFIN
          "rfd": 0,          // delta REFIN
          "frd": 0,          // delta FAL/RJ
          "sd": -15,         // delta score
          "lim": false,      // é liminar?
          "ma": ["PEFIN_NOVO"], // alertas mais atenção
          "ni": [ ... ],     // novos itens
          "ri": [ ... ]      // itens removidos
        }
      ]
    }
  }
}
```

---

## Segmentos Serasa Monitore reconhecidos

| Segmento | Descrição |
|----------|-----------|
| 040101 | PEFIN — Pendências Financeiras |
| 040102 | REFIN — Refinanciamentos |
| 040199 | PEFIN Nada Consta |
| 040202 | Pendências (Protestos, Ações Judiciais, Dívidas) |
| 040299 | Pendências Nada Consta |
| 040601 | Falência / Recuperação Judicial |
| 041099 | Geral Nada Consta |
| 571001 | Score Serasa |
| 010102 | Razão Social |

---

## Requisitos Python

Python 3.8+ sem dependências externas.

```bash
python parse.py --help
```
