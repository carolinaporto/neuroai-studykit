# `content/`

Esta pasta guarda o material de aula do GENED 1201 — PDFs, slides e transcrições — que é
a **fonte primária** de onde as questões são geradas.

**O conteúdo desta pasta é deliberadamente ausente deste repositório.** O material do curso
é de seus autores; não é meu para redistribuir. O `.gitignore` mantém tudo aqui fora do
versionamento, exceto este arquivo.

Para rodar o projeto com material próprio:

```bash
mkdir -p content/week01
# coloque seus PDFs / .pptx / .vtt aqui
python -m ingest.cli sync content/week01
```

Para ver o pipeline funcionando sem nenhum material de curso, use o corpus sintético do
repositório — textos curtos escritos por mim sobre conceitos básicos de neurociência e
aprendizado de máquina:

```bash
python -m ingest.cli sync tests/fixtures/
```
