import yaml

# Supondo a leitura do arquivo YAML ou de uma string
with open("scraper_config.yaml", "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

# 1. Acesso à lista de turmas ('classes')
classes = config.get("classes", [])

for turma in classes:
    class_id = turma.get("class_id")
    print(f"Turma ID: {class_id}")

    # Acesso às evidências da turma
    evidences = turma.get("evidences", {})

    # 2. Acesso aos itens de 'monitoring'
    monitoring_items = evidences.get("monitoring", [])
    print("  Itens de Monitoring:")
    for item in monitoring_items:
        title = item.get("title")
        quiz_id = item.get("quiz_id")
        print(f"    - Título: {title}, Quiz ID: {quiz_id}")

    # 3. Acesso aos itens de 'consolidation' (se necessário)
    consolidation_items = evidences.get("consolidation", [])
    print("  Itens de Consolidation:")
    for item in consolidation_items:
        title = item.get("title")
        gradebook_name = item.get("gradebook_name")
        deadline_quiz_id = item.get("deadline_quiz_id")
        deadline = item.get("deadline")
        print(
            f"    - Título: {title}, Gradebook: {gradebook_name}, Deadline: {deadline_quiz_id}/{deadline}"
        )
        print(type(deadline))