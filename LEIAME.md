# Disparador de notícias Huntter News

- `coletor.py`: busca as notícias (edite a lista FONTES para trocar ou incluir sites).
- `.github/workflows/disparador.yml`: roda o coletor de hora em hora.
- `noticias.json`: as notícias coletadas (atualizado sozinho).
- `index.html`: o bloco de notícias que aparece no site.

Código para o widget "Código HTML" do painel bs7 (troque SEU-USUARIO):

<iframe src="https://SEU-USUARIO.github.io/disparador-noticias/?limite=10" style="width:100%;height:720px;border:0" loading="lazy" title="Plantão de notícias"></iframe>

Opções no endereço: ?limite=8 (quantidade), &grupo=Maranhão ou &grupo=Brasil (filtro inicial).
Para disparar na hora: aba Actions > Disparador de notícias > Run workflow.
