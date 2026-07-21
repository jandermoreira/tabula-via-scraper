# Especificação Técnica: Scraper Moodle → Firestore

## 1. Objetivo

Extrair evidências de aprendizagem (notas e prazos) do Moodle e armazená-las no Firestore.

---

# 2. Estrutura de Destino (Firestore)

O scraper deve organizar os dados em dois níveis:

* **Metadados da Turma (Timeline)**
* **Evidências do Aluno**

## 2.1 Metadados da Turma (Timeline)

Armazena as informações de cada atividade da turma.

**Caminho:**

```text
turmas/{classId}/activities_metadata/{activityId}
```

### Campos

| Campo      | Tipo      | Descrição                                                                          |
| ---------- | --------- | ---------------------------------------------------------------------------------- |
| `title`    | String    | Nome da atividade (ex.: "Lista 1", "Prova Final").                                 |
| `type`     | String    | `MONITORING` (listas, exercícios etc.) ou `CONSOLIDATION` (provas, projetos etc.). |
| `deadline` | Timestamp | Data de entrega ou realização da atividade no Moodle.                              |

---

## 2.2 Evidências do Aluno

Armazena o desempenho individual em cada atividade.

### Caminhos

**Acompanhamento**

```text
turmas/{classId}/alunos/{studentId}/monitoring_evidence/{activityId}
```

**Consolidação**

```text
turmas/{classId}/alunos/{studentId}/consolidation_evidence/{activityId}
```

### Campos

| Campo   | Tipo          | Descrição                                                                                   |
| ------- | ------------- | ------------------------------------------------------------------------------------------- |
| `score` | Number | null | Nota obtida. Deve ser `null` quando a atividade não foi realizada ou ainda não possui nota. |

---

# 3. Lógica de Extração e Sincronização

## 3.1 Mapeamento de Tipos

O scraper deve classificar cada atividade com base na estrutura do Moodle (por exemplo, categorias de notas ou prefixos no nome).

| Tipo no Moodle                                          | Tipo no Firestore |
| ------------------------------------------------------- | ----------------- |
| Atividades de processo (quizzes, tarefas semanais etc.) | `MONITORING`      |
| Avaliações somativas (provas, exames, projetos etc.)    | `CONSOLIDATION`   |

---

## 3.2 Gestão de Ausências

Caso um aluno esteja matriculado, mas não possua registro para uma atividade existente em `activities_metadata`, o scraper deve criar o documento correspondente com:

```json
{
  "score": null
}
```

---

## 3.3 Periodicidade e Atualização

O scraper deve executar sincronizações periódicas.

Durante cada sincronização, deve:

* atualizar o campo `score` quando houver alteração da nota;
* manter os demais dados inalterados;
* remover de `activities_metadata` as atividades excluídas do Moodle.

---

# 4. Requisitos de Consistência

## 4.1 IDs Únicos

O identificador `activityId` deve ser o mesmo:

* em `activities_metadata`;
* nos registros de evidências dos alunos.

---

## 4.2 Tratamento de Escopo

O scraper deve interromper a sincronização de alunos que:

* trancaram a disciplina;
* foram removidos da turma.

---

## 4.3 Cronologia

A ordem temporal das atividades deve ser determinada exclusivamente pelo campo `deadline` presente em `activities_metadata`.

O scraper não deve depender da ordem alfabética dos nomes das atividades.

---

# 5. Fluxo de Operação

```text
1. Scan
   └── Lê a estrutura de notas da turma no Moodle.

2. Sync Metadata
   └── Atualiza activities_metadata.

3. Sync Students
   ├── Atualiza monitoring_evidence.
   └── Atualiza consolidation_evidence.
```
