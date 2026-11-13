"""
Disparador de notícias da Rádio/TV Huntter News.
Roda de hora em hora no GitHub Actions, busca as manchetes novas
do g1 e do Imirante e grava tudo em noticias.json, que o widget lê.
Usa só a biblioteca padrão do Python (não precisa instalar nada).
"""
import json, re, html, os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

# ---------- CONFIGURAÇÃO: edite aqui as fontes ----------
FONTES = [
    {"nome": "g1 Maranhão", "grupo": "Maranhão", "tipo": "rss",
     "url": "https://g1.globo.com/rss/g1/ma/maranhao/"},
    {"nome": "g1", "grupo": "Brasil", "tipo": "rss",
     "url": "https://g1.globo.com/rss/g1/"},
    {"nome": "Imirante", "grupo": "Maranhão", "tipo": "pagina",
     "url": "https://imirante.com/noticias",
     "padrao": r"(?:https?://imirante\.com)?/noticias/[a-z0-9\-/]+/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+"},
]
POR_FONTE = 12          # quantas notícias novas pegar de cada fonte por rodada
MAXIMO_TOTAL = 60       # quantas notícias manter no arquivo
TAMANHO_RESUMO = 180    # caracteres do resumo exibido
ARQUIVO = "noticias.json"
# ---------------------------------------------------------

UA = "Mozilla/5.0 (compatible; HuntterNewsBot/1.0; +https://radiohuntternews.bs7.com.br)"


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR"})
    with urllib.request.urlopen(req, timeout=25) as r:
        bruto = r.read()
        cs = r.headers.get_content_charset() or "utf-8"
    return bruto.decode(cs, errors="replace")


def limpar(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def resumir(texto):
    texto = limpar(texto)
    if len(texto) <= TAMANHO_RESUMO:
        return texto
    corte = texto[:TAMANHO_RESUMO].rsplit(" ", 1)[0]
    return corte.rstrip(",.;:") + "…"


def agora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_iso(valor):
    if not valor:
        return None
    try:
        return parsedate_to_datetime(valor).astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def meta(pagina, chave):
    """Lê <meta property|name="chave" content="..."> em qualquer ordem de atributos."""
    for tag in re.findall(r"<meta\b[^>]*>", pagina, flags=re.I):
        if re.search(r'(?:property|name)\s*=\s*["\']' + re.escape(chave) + r'["\']', tag, flags=re.I):
            m = re.search(r'content\s*=\s*["\']([^"\']*)["\']', tag, flags=re.I)
            if m:
                return html.unescape(m.group(1)).strip()
    return None


def ler_rss(fonte, xml_texto):
    itens = []
    raiz = ET.fromstring(xml_texto.encode("utf-8"))
    ns_media = "{http://search.yahoo.com/mrss/}"
    for item in raiz.iter("item"):
        titulo = limpar(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not titulo or not link:
            continue
        descricao = item.findtext("description") or ""
        imagem = None
        for tag in (ns_media + "content", ns_media + "thumbnail", "enclosure"):
            el = item.find(tag)
            if el is not None and el.get("url"):
                imagem = el.get("url")
                break
        if not imagem:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)', descricao)
            imagem = m.group(1) if m else None
        itens.append({
            "titulo": titulo, "link": link, "resumo": resumir(descricao),
            "imagem": imagem, "data": data_iso(item.findtext("pubDate")) or agora_iso(),
        })
        if len(itens) >= POR_FONTE:
            break
    return itens


def ler_pagina(fonte, pagina, ja_vistos):
    # 1) Se o site anunciar um feed RSS, usa ele.
    m = re.search(r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*>', pagina, flags=re.I)
    if m:
        href = re.search(r'href=["\']([^"\']+)', m.group(0))
        if href:
            try:
                return ler_rss(fonte, baixar(urljoin(fonte["url"], href.group(1))))
            except Exception as e:
                print(f"  feed anunciado falhou ({e}), lendo a página")
    # 2) Senão, pega os links de matérias e lê os metadados de cada uma.
    links = []
    for link in re.findall(fonte["padrao"], pagina):
        link = urljoin(fonte["url"], link)
        if link not in links and "/amp/" not in link:
            links.append(link)
    itens = []
    for link in links:
        if len(itens) >= POR_FONTE:
            break
        if link in ja_vistos:
            continue
        try:
            materia = baixar(link)
        except Exception as e:
            print(f"  não abriu {link}: {e}")
            continue
        titulo = meta(materia, "og:title") or ""
        titulo = re.sub(r"\s*-\s*Imirante\.com\s*$", "", titulo).strip()
        if not titulo:
            continue
        itens.append({
            "titulo": titulo, "link": link,
            "resumo": resumir(meta(materia, "og:description") or meta(materia, "description") or ""),
            "imagem": meta(materia, "og:image"),
            "data": data_iso(meta(materia, "article:published_time")) or agora_iso(),
        })
    return itens


def main():
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            atual = json.load(f)
    except Exception:
        atual = {"noticias": []}
    por_link = {n["link"]: n for n in atual.get("noticias", [])}
    novas = 0

    for fonte in FONTES:
        print(f"> {fonte['nome']}")
        try:
            conteudo = baixar(fonte["url"])
            if fonte["tipo"] == "rss":
                itens = ler_rss(fonte, conteudo)
            else:
                itens = ler_pagina(fonte, conteudo, por_link)
        except Exception as e:
            print(f"  erro: {e}")
            continue
        for it in itens:
            it["fonte"] = fonte["nome"]
            it["grupo"] = fonte["grupo"]
            if it["link"] not in por_link:
                novas += 1
                por_link[it["link"]] = it
        print(f"  {len(itens)} lidas")

    lista = sorted(por_link.values(), key=lambda n: n.get("data") or "", reverse=True)[:MAXIMO_TOTAL]
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump({"atualizado": agora_iso(), "noticias": lista}, f, ensure_ascii=False, indent=1)
    print(f"Pronto: {novas} novas, {len(lista)} no total.")


if __name__ == "__main__":
    main()
