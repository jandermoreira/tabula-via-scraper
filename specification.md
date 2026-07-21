Especificação Técnica: Scraper Moodle → Firestore
1. Objetivo
Extrair evidências de aprendizagem (notas e prazos) do Moodle e organizá-las no Firestore para que o aplicativo possa calcular, sob demanda, o estado de acompanhamento dos alunos (Domínio, Evolução, Consistência e Intervenção).
2. Estrutura de Destino (Firestore)
O scraper deve organizar os dados em dois níveis: Metadados da Turma (o mapa cronológico) e Evidências do Aluno (as notas).
2.1 Metadados da Turma (Timeline)
Define a ordem e a finalidade pedagógica de cada atividade.
•
Caminho: turmas/{classId}/activities_metadata/{activityId}
•
Campos:
◦
title: (String) Nome da atividade (ex: "Lista 1", "Prova Final").
◦
type: (String) MONITORING (para listas/exercícios) ou CONSOLIDATION (para provas/projetos).
◦
deadline: (Timestamp) Data de entrega ou realização no Moodle. Serve como a âncora cronológica para todos os alunos.
◦
weight: (Number) [Opcional] Peso da atividade no cálculo.
2.2 Evidências do Aluno
Armazena o desempenho individual.
•
Caminho (Acompanhamento): turmas/{classId}/alunos/{studentId}/monitoring_evidence/{activityId}
•
Caminho (Consolidação): turmas/{classId}/alunos/{studentId}/consolidation_evidence/{activityId}
•
Campos:
◦
score: (Number | null) A nota obtida. Deve ser null se a atividade não foi realizada ou não possui nota.
◦
updatedAt: (Timestamp) Momento da última extração pelo scraper.
3. Lógica de Extração e Sincronização
3.1 Mapeamento de Tipos
O scraper deve classificar as atividades baseando-se na estrutura do Moodle (ex: Categorias de Notas ou prefixos no nome):
•
Atividades de processo (quizzes, tarefas semanais) → MONITORING.
•
Avaliações somativas (provas, exames) → CONSOLIDATION.
3.2 Gestão de Ausências
•
Se um aluno está matriculado mas não possui registro de entrega para uma atividade presente no activities_metadata, o scraper deve criar o documento do aluno com score: null.
•
Isso é vital para que o aplicativo identifique falhas de ritmo e mude o estado do aluno para "Priority" ou "Directed Review".
3.3 Periodicidade e Atualização
•
O scraper deve realizar varreduras periódicas.
•
Ao detectar uma mudança de nota no Moodle, deve atualizar apenas o campo score e updatedAt.
•
Caso uma atividade seja removida do Moodle, o scraper deve remover o registro correspondente em activities_metadata (o app reagirá limpando o histórico e recalculando os estados dos alunos).
4. Requisitos de Consistência
1.
IDs Únicos: O activityId deve ser consistente entre o metadado da turma e o registro do aluno para permitir o cruzamento (join) sob demanda no dispositivo.
2.
Tratamento de Escopo: O scraper deve garantir que alunos que trancaram a disciplina ou saíram da turma tenham seus registros cessados para evitar diagnósticos falsos de "Recuperação".
3.
Cronologia: O campo deadline em activities_metadata é a única fonte de verdade para a ordem das evidências. O scraper não deve confiar na ordem alfabética dos nomes das atividades.
5. Fluxo de Operação
1.
Scan: Scraper lê a estrutura de notas da turma no Moodle.
2.
Sync Metadata: Atualiza a cronologia da turma em activities_metadata.
3.
Sync Students: Para cada aluno, atualiza monitoring_evidence e consolidation_evidence.
4.
Finish: O Firestore notifica o aplicativo Tabula Via via Snapshot Listeners, disparando o cálculo automático dos quatro registros de acompanhamento.