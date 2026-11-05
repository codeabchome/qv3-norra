#!/usr/bin/env python3
"""Ücretsiz çeviri (Google gtx ucu, anahtarsız). Kullanım: python c/cevir.py c/girdi/<parti>.json c/sonuc/<parti>/
Girdi: [{anahtar, slug, slug_en, sembol, baslik, seo_baslik, aciklama, kisaca, icerik}, ...] (TR)
Çıktı: <dil>.json (aynı sıra) + rapor.json. Günlüğe metin basılmaz (açık depo)."""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

DILLER = 'en de ar az bn nl fr hi id it ja ms pt ru zh es th ug ur'.split()
LATIN = {'en', 'de', 'nl', 'fr', 'it', 'es', 'pt', 'id', 'ms', 'az'}
KOD = {'zh': 'zh-CN'}
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
ARA = float(os.environ.get('ARA', '0.4'))
# "God" -> "Allah" (yalnız tam sözcük; ja/zh'de 神 bileşik sözcüklerde geçtiği için dokunulmaz, zh yalnız 上帝)
ALLAH = {
    'en': [('God', 'Allah')], 'nl': [('God', 'Allah')], 'de': [('Gottes', 'Allahs'), ('Gott', 'Allah')],
    'fr': [('Dieu', 'Allah')], 'es': [('Dios', 'Alá')], 'it': [('Dio', 'Allah')], 'pt': [('Deus', 'Allah')],
    'ru': [('Богом', 'Аллахом'), ('Богу', 'Аллаху'), ('Бога', 'Аллаха'), ('Бог', 'Аллах')],
    'id': [('Tuhan', 'Allah')], 'ms': [('Tuhan', 'Allah')], 'zh': [('上帝', '安拉')],
}
# Âlim adları çeviriden ÖNCE uluslararası yazıma çevrilir (Google Türkçe yazımı olduğu gibi bırakıyor)
ADLAR = [("Cafer-i Sâdık", "Ja'far al-Sadiq"), ("Cafer-i Sadık", "Ja'far al-Sadiq"), ("Câbir el-Mağribî", "Jabir al-Maghribi"),
         ("Ebû Saîd el-Vâiz", "Abu Sa'id al-Wa'iz"), ("İbn Sîrîn", "Ibn Sirin"), ("İbn Sirin", "Ibn Sirin"),
         ("Kirmânî", "al-Kirmani"), ("Nablusî", "al-Nabulsi")]
def adlar(s):
    for a, b in ADLAR: s = s.replace(a, b)
    return s
yapi = lambda h: re.findall(r'</?b\b', h)
ist = {'istek': 0, 'karakter': 0, 'hata': [], 'allah_duzeltme': 0, 'tekrar': 0}

def _get(dil, metinler):
    q = 'client=gtx&sl=tr&tl=' + KOD.get(dil, dil) + '&format=html' + ''.join('&q=' + urllib.parse.quote(m) for m in metinler)
    for bekle in (0, 5, 20, 60, 180):
        if bekle: time.sleep(bekle); ist['tekrar'] += 1
        try:
            r = urllib.request.urlopen(urllib.request.Request('https://translate.googleapis.com/translate_a/t?' + q, headers={'User-Agent': UA}), timeout=40)
            v = json.loads(r.read().decode('utf-8'))
            ist['istek'] += 1; ist['karakter'] += sum(len(m) for m in metinler)
            time.sleep(ARA)
            if isinstance(v, str): v = [v]
            out = [(t[0] if isinstance(t, list) else t) for t in v]
            if len(out) != len(metinler): raise ValueError(f'sayi {len(out)}/{len(metinler)}')
            return out
        except Exception as e:
            ist['hata'].append(f'{dil}: {type(e).__name__} {getattr(e, "code", "")} {str(e)[:60]}')
    raise SystemExit(f'{dil}: tekrar denemeler tükendi')

def cevir(dil, metinler, sinir=5500):
    """URL uzunluğuna göre gruplar; sonuç sırası korunur."""
    out, grup, boy = [], [], 0
    for m in metinler:
        b = len(urllib.parse.quote(m)) + 3
        if grup and boy + b > sinir:
            out += _get(dil, grup); grup, boy = [], 0
        grup.append(m); boy += b
    if grup: out += _get(dil, grup)
    for i, (m, o) in enumerate(zip(metinler, out)):   # boş ya da <b> sayısı bozuk parça → tek başına yeniden
        if (m.strip() and not o.strip()) or yapi(m) != yapi(o):
            ist['tek_tekrar'] = ist.get('tek_tekrar', 0) + 1
            o2 = _get(dil, [m])[0]
            if o2.strip() and yapi(m) == yapi(o2): out[i] = o2
            else: ist['hata'].append(f'{dil}: parca duzelmedi #{i}')
    return out

def temizle(dil, s):
    s = html.unescape(s).replace('​', '').strip()
    s = re.sub(r'\s*<b>\s*', ' <b>', s); s = re.sub(r'\s*</b>\s*', '</b> ', s)
    s = re.sub(r'^ <b>', '<b>', s); s = re.sub(r' {2,}', ' ', s).strip()
    for a, b in ALLAH.get(dil, []):
        s, n = re.subn(r'(?<![\w])' + re.escape(a) + r'(?![\w])', b, s); ist['allah_duzeltme'] += n
    return s

AZ = str.maketrans({'ə': 'e', 'Ə': 'e', 'ı': 'i', 'İ': 'i', 'ş': 's', 'Ş': 's', 'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g', 'ö': 'o', 'Ö': 'o', 'ü': 'u', 'Ü': 'u', 'ß': 'ss'})
def slugla(s):
    s = unicodedata.normalize('NFKD', s.translate(AZ)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def kirp(s, n):
    if len(s) <= n: return s
    k = s[:n - 1]; k = k[:k.rfind(' ')] if ' ' in k else k
    return k.rstrip(' ,;:.-–') + '…'

def main(girdi, cikti):
    tr = json.load(open(girdi, encoding='utf-8'))
    os.makedirs(cikti, exist_ok=True)
    t0 = time.time(); rapor = {}
    for dil in DILLER:
        d0 = time.time(); sonuc = []; slugs = set()
        ek = cevir(dil, ['İslami Rüya Tabiri'])[0]
        for t in tr:
            bloklar = re.findall(r'<(h2|p)>(.*?)</\1>', t['icerik'], re.S)
            alan = [t['sembol'], t['baslik'], t['seo_baslik'], t['aciklama'], t['kisaca']]
            c = [temizle(dil, x) for x in cevir(dil, [adlar(x) for x in alan + [b for _, b in bloklar]])]
            sembol, baslik, seo, acik, kisa = c[:5]
            icerik = ''.join(f'<{tag}>{x}</{tag}>' for (tag, _), x in zip(bloklar, c[5:]))
            if len(seo) > 65:
                seo = baslik + ' | ' + ek if len(baslik + ' | ' + ek) <= 65 else kirp(baslik, 65)
            if dil == 'en': slug = t['slug_en']
            elif dil in LATIN:
                slug = slugla(re.sub(r'[|:?!].*$', '', baslik))
                if slug == t['slug_en'] or not slug: slug = slugla(baslik) + '-' + dil
            else: slug = t['slug_en']
            if slug in slugs: slug += '-' + dil
            slugs.add(slug)
            sonuc.append({'anahtar': t['anahtar'], 'slug': slug, 'sembol': sembol.strip(' .'), 'baslik': baslik.strip(' .'),
                          'seo_baslik': seo, 'aciklama': kirp(acik, 160), 'kisaca': kisa, 'icerik': icerik})
        json.dump(sonuc, open(os.path.join(cikti, dil + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        rapor[dil] = round(time.time() - d0, 1)
        print(dil, 'tamam', rapor[dil], 'sn', flush=True)
    ist['dil_sn'] = rapor; ist['toplam_sn'] = round(time.time() - t0, 1); ist['tabir'] = len(tr)
    json.dump(ist, open(os.path.join(cikti, 'rapor.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('istek', ist['istek'], 'karakter', ist['karakter'], 'hata', len(ist['hata']), 'sn', ist['toplam_sn'])

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
