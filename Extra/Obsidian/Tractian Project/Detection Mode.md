---
tags: [domain, detection]
aliases: [Detection Mode, Modo de Detecção]
---

# Detection Mode

## Como a falha foi detectada
- **`baseline`** — desvio do aprendido (desalinhamento, desbalanceamento, rolamento,
  elétrica). **Exige baseline \`established\`**.
- **`symptom`** — sintoma por si só já indica a falha (ex.: lubrificação). Independe
  do baseline.

## Por que importa
Se o insight usa `detection_mode: baseline` mas o baseline não está `established`, o
diagnóstico **não é confiável** → verificar [[Baseline]] antes de confiar.
