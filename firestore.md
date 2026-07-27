# Especificação do Banco de Dados: Cloud Firestore (Tabula Via)

## 1. Padrões de Dados

- **Identificadores (IDs):** Todas as chaves primárias são Strings contendo UUID v4.
- **Identidade de Documento:** O ID atribuído ao documento na coleção deve ser idêntico ao valor armazenado no campo de ID dentro do conteúdo do documento.
- **Datas/Tempo:** Armazenadas como Números Inteiros (milissegundos desde o Unix Epoch).
- **Textos/Enums:** Armazenados como Strings. Valores de estado (Enums) são sempre em MAIÚSCULAS.

## 2. Hierarquia de Coleções

Os dados são organizados por usuário e por turma.

O caminho base é:

```text
/users/{userEmail}/
```

O `userEmail` é o email do usuário autenticado via Google OAuth. Isso garante consistência entre diferentes clientes (scraper e app Android) que usam o mesmo email para autenticação.

### Coleção: `classes`

Armazena os dados das turmas.

**ID do Documento:** `{classId}` (UUID)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| classId | String | Identificador único da turma. |
| className | String | Nome da disciplina ou turma. |
| academicYear | String | Ano letivo (ex: "2024"). |
| period | String | Período/Semestre (ex: "1º Semestre"). |
| numberOfClasses | Number | Quantidade total de aulas previstas. |

### Coleção: `students` (Subcoleção de Turma)

Alunos vinculados a uma turma específica.

**Caminho:**

```text
/users/{userEmail}/classes/{classId}/students/
```

**ID do Documento:** `{studentId}` (UUID)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| studentId | String | Identificador único do aluno. |
| name | String | Nome completo legal do aluno. |
| displayName | String | Nome para exibição ou apelido. |
| studentNumber | String | Número de matrícula ou chamada. |
| classId | String | Referência à turma pai. |
| status | String | Estados: ACTIVE, INACTIVE ou CANCELLED. |

### Coleção: `skills` (Subcoleção de Turma)

Critérios de avaliação definidos para a turma.

**Caminho:**

```text
/users/{userEmail}/classes/{classId}/skills/
```

**ID do Documento:** `{skillId}` (UUID)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| skillId | String | Identificador único da habilidade. |
| name | String | Nome da competência avaliada. |
| description | String | Descrição detalhada do critério. |
| classId | String | Referência à turma pai. |

### Coleção: `activities` (Subcoleção de Turma)

Registros de atividades ou aulas ocorridas.

**Caminho:**

```text
/users/{userEmail}/classes/{classId}/activities/
```

**ID do Documento:** `{activityId}` (UUID)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| activityId | String | Identificador único da atividade. |
| name | String | Título da atividade/aula. |
| date | Number | Data da atividade em milissegundos. |
| description | String | Classificação: "Individual" ou "Group". |
| classId | String | Referência à turma pai. |

## 3. Regras de Escrita e Integridade

1. **Geração de Documentos:** Ao criar um novo registro (ex: um aluno), gere um UUID v4. Use este UUID para nomear o documento no Firestore e preencha o campo de ID interno (ex: studentId) com este mesmo valor.

2. **Valor Padrão de Status:** Todo novo aluno criado deve ser salvo com o campo `status` definido como `"ACTIVE"`.

3. **Preservação de Dados:** Ao atualizar um documento existente, certifique-se de enviar todos os campos obrigatórios. O sistema opera com substituição total do documento durante a sincronização entre dispositivos.

4. **Consistência de Nomes:** Utilize exatamente os nomes de campos listados nas tabelas acima (ex: use `className` e não `name` para turmas; use `classId` e não `id_turma`).