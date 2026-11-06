#!/usr/bin/env python3
"""Otomatik çeviri: siteden Türkçesi yüklenmiş taslakların eksik dillerini çeker, ücretsiz çevirir,
denetler, geri yollar. Kimlik: GitHub OIDC (kapak hattıyla aynı). Günlüğe metin basılmaz.
Ortam: SITE (secret), SINIR (koşu başına en çok tabir, vars. 15), SURE (dk, vars. 45)."""
import json, os, re, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import cevir as C

YOL = '/wp-json/dkr/v1/ceviri'
AUD = 'qv3-norra'
_j = {'v': None, 'z': 0}
TRH = re.compile(r'[ğışĞİŞ]')
yapi = lambda h: re.findall(r'</?(?:h2|p|b)\b', h)
duz = lambda h: re.sub('<[^>]+>', '', h)

def jeton():
    if _j['v'] and time.time() - _j['z'] < 240: return _j['v']
    r = urllib.request.Request(os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=' + AUD,
                               headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(r, timeout=30) as y: _j['v'] = json.loads(y.read())['value']
    _j['z'] = time.time(); return _j['v']

def site(yol, govde=None):
    r = urllib.request.Request(os.environ['SITE'].rstrip('/') + yol, method='POST' if govde is not None else 'GET',
                               data=None if govde is None else json.dumps(govde, ensure_ascii=False).encode('utf-8'))
    r.add_header('X-DK-Kapak-Jeton', jeton()); r.add_header('User-Agent', C.UA); r.add_header('Cache-Control', 'no-cache')
    if govde is not None: r.add_header('Content-Type', 'application/json; charset=utf-8')
    for d in range(3):
        try:
            with urllib.request.urlopen(r, timeout=90) as y: return json.loads(y.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code < 500 or d == 2: raise SystemExit(f'site HTTP {e.code}')
        except Exception as e:
            if d == 2: raise SystemExit(f'site {type(e).__name__}')
        time.sleep(10 * (d + 1))

def tek(dil, tr, slug_en):
    bl = re.findall(r'<(h2|p)>(.*?)</\1>', tr['icerik'], re.S)
    alan = [tr['sembol'], tr['baslik'], tr['seo_baslik'], tr['aciklama'], tr['kisaca']]
    c = [C.temizle(dil, x) for x in C.cevir(dil, [C.adlar(x) for x in alan + [b for _, b in bl]])]
    sembol, baslik, seo, acik, kisa = c[:5]
    icerik = ''.join(f'<{t}>{x}</{t}>' for (t, _), x in zip(bl, c[5:]))
    ek = C.EK[dil]
    if len(seo) > 65: seo = baslik + ' | ' + ek if len(baslik + ' | ' + ek) <= 65 else C.kirp(baslik, 65)
    if dil == 'en': slug = slug_en or C.slugla(re.sub(r'[|:?!].*$', '', baslik))
    elif dil in C.LATIN:
        slug = C.slugla(re.sub(r'[|:?!].*$', '', baslik))
        if not slug or slug == slug_en: slug = (slug or slug_en) + '-' + dil
    else: slug = slug_en
    return {'slug': slug, 'sembol': sembol.strip(' .'), 'baslik': baslik.strip(' .'), 'seo_baslik': seo,
            'aciklama': C.kirp(acik, 160), 'kisaca': kisa, 'icerik': icerik}

def denet(dil, o, tr):
    for a in ('slug', 'sembol', 'baslik', 'icerik', 'kisaca'):
        if not str(o.get(a, '')).strip(): return a + ' boş'
    if yapi(o['icerik']) != yapi(tr['icerik']): return 'yapı'
    tum = ' '.join(str(o[a]) for a in ('sembol', 'baslik', 'seo_baslik', 'aciklama', 'kisaca', 'icerik'))
    if dil not in ('az',) and TRH.search(tum): return 'Türkçe harf'
    if re.search(r'Meclis[iîı]|Majlis|Danyal|Çağdaş|Bursal|Paksu|Tiflis|Türkoğlu', tum, re.I): return 'yasak ad'
    oran = len(duz(o['icerik'])) / max(1, len(duz(tr['icerik'])))
    if oran < (0.22 if dil in ('zh', 'ja') else 0.35): return 'kısa'
    if dil in C.LATIN and not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', o['slug']): return 'slug'
    return ''

def main():
    sinir, bitis = int(os.environ.get('SINIR', '15')), time.time() + 60 * int(os.environ.get('SURE', '45'))
    ist = {'tabir': 0, 'dil': 0, 'kuyruga': 0, 'red': 0, 'cakisma': 0}
    gorulen = set()                                     # bu koşuda işlenen taslak bir daha çevrilmez (reddedilen dil kalsa bile)
    while ist['tabir'] < sinir and time.time() < bitis:
        b = site(YOL + '/bekleyen?adet=50')
        yeni = [it for it in b.get('ogeler', []) if it['anahtar'] not in gorulen]
        if not yeni: break
        for it in yeni:
            if ist['tabir'] >= sinir or time.time() > bitis: break
            gorulen.add(it['anahtar'])
            tr, eksik, slug_en = it['tr'], [d for d in it['eksik'] if d != 'tr'], it.get('en_slug')
            if not eksik: continue
            sira = (['en'] if 'en' in eksik else []) + [d for d in eksik if d != 'en']
            diller = {}
            for dil in sira:
                o = tek(dil, tr, slug_en)
                if dil == 'en': slug_en = o['slug']
                n = denet(dil, o, tr)
                if n: ist['red'] += 1; print('red', dil, n, flush=True); continue
                diller[dil] = o
            if not diller: continue
            y = site(YOL, {'anahtar': it['anahtar'], 'diller': diller})
            for dil in y.get('cakisan', []):          # adres çakışması → "-<dil>" ekiyle bir kez daha
                ist['cakisma'] += 1
                if diller[dil]['slug'].endswith('-' + dil): continue   # ek zaten var → raporda kalır, elle bakılır
                diller[dil]['slug'] += '-' + dil
                y2 = site(YOL, {'anahtar': it['anahtar'], 'diller': {dil: diller[dil]}})
                y['kaydedilen'] += y2.get('kaydedilen', []); y['kuyruga'] = y['kuyruga'] or y2.get('kuyruga')
            ist['tabir'] += 1; ist['dil'] += len(y.get('kaydedilen', [])); ist['kuyruga'] += int(bool(y.get('kuyruga')))
            ist['red'] += len([d for d in (y.get('reddedilen') or {}) if d not in y.get('cakisan', [])])
            print('tabir', ist['tabir'], 'dil', len(y.get('kaydedilen', [])), 'kuyruk' if y.get('kuyruga') else '', flush=True)
    print(json.dumps(ist), 'istek', C.ist['istek'], 'karakter', C.ist['karakter'], 'hata', len(C.ist['hata']))

if __name__ == '__main__':
    if not os.environ.get('SITE'): print('SITE yok'); sys.exit(0)
    main()
