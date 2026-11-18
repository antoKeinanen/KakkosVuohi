"""
All printable strings of the bot (Finnish, as in the previous version).

The strings are Telegram HTML (the bot's default parse mode), so a static string may use <b>, and
every *dynamic* value that is placed into one MUST go through formatting.esc() when it is user
controlled (nicknames, chat titles, ...). Placeholders are str.format() fields.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _ns(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    return value


_STRINGS = {
    "emoji": {
        "beer": "🍺",
        "beers": "🍻",
        "wine": "🍷",
        "glasses": "🥂",
        "shot": "🥃",
        "pencil": "✏",
        "memo": "📝",
        "cross": "❌",
        "gear": "⚙",
        "person_silhouette": "👤",
        "scale": "⚖",
        "ruler": "📏",
        "female": "♀",
        "male": "♂",
        "trash": "🗑",
        "refresh": "🔃",
        "glowing_star": "🌟",
        "stopwatch": "⏱",
        "floppy_disk": "💾",
        "bar_graph": "📊",
        "info": "ℹ",
        "goat": "🐐",
        "drink": "🍹",
    },
    "drink_responses": [
        "Bäää.",
        "Uuteen nousuun.",
        "Muista juoda vettä!",
        "Aamu alkaa A:lla.",
        "Muista juoda vettä!",
        "Juo viinaa, viina on hyvää.",
        "Meno on meno.",
        "Lörs lärä, viinaa!",
        "Muista juoda vettä!",
        "Bäätöntä menoa!",
        "Loers laerae, booze!",
        "Remember to drink water!",
        "To the new rise.",
        "Go is go.",
        "Morning begins with A",
        "Drink booze, booze is good.",
    ],
    "short_permilles_text": "<b>Nyt:</b> {permilles}‰ - <b>30min:</b> {permilles30Min}‰",
    "long_permilles_text": "<b>Nyt:</b> {permilles}‰ - <b>30min:</b> {permilles30Min}‰.\nVeressäsi on {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Olet selvinpäin {hours}h {minutes}min päästä.\n\nViimeisen kolmen päivän tapahtumat:\n{drinkList72h}",
    "gender": {"male": "Mies", "female": "Nainen"},
    "yes": "Kyllä",
    "no": "Ei",
    "no_1st": "En",
    "commands": {
        "blakkis": {
            "please_update_user_info": "Päivitä käyttäjätietosi käyttämällä komentoa /tunnus.",
            "announcements": "Ilmoituksia:\n\n{announcements}",
            "unauthorized": "Ei käyttöoikeutta.",
            "user404": "Rekisteröidy ensiksi käyttämällä komentoa /tunnus.",
            "help_text": "KakkosVuohi korvaa BläkkisVuohen. Vanhan botin tunnukset ja tiedot eivät siirtyneet, joten luo uusi tunnus.\n\nKakkosVuohi auttaa sinua ja ystäviäsi seuraamaan rippauksesi (lue: promillejesi) tasoa. Aloita komennolla /start tai seuraa näitä ohjeita.\n\nLuo ensimmäiseksi tunnus komennolla /tunnus. Tunnuksen luomisen jälkeen voit alkaa kellottamaan juomia sisään komennolla /juoma. Annan sinulle arvioita rippauksesta komennolla /promillet. Minut voi myös lisätä ryhmään, jolloin kerron /promillet-komennolla kaikkien ryhmässä olevien rippitasot. Jokaisen ryhmäläisen täytyy kuitenkin sanoa ryhmässä /moro, jotta he pääsevät rippilistaukseen mukaan.",
            "cmd_list": "Komennot\n\n{cmd_list}",
            "use_only_in_private": "Käytä komentoa vain minun kanssa privaviestinä!",
            "use_only_in_chats": "Käytä komentoa vain chateissa!",
            "command_not_found": "Mitä? Jos kaipaat apua käyttämiseen, kirjoita /help",
            "command_error": "Virhe! Komennon käyttöohje: {cmd_help}",
            "error": "Vakava virhe! Aloita komento alusta, niin yleensä poistuu sillä.",
            "back": "« Takaisin",
        },
        "about": {
            "cmd_description": "/about - About the bot",
            "text": "KakkosVuohi estimates blood alcohol concentration from the drinks you log. It is free, open source and licensed under GPLv3. The source code is at https://github.com/antoKeinanen/KakkosVuohi. It continues BläkkisVuohi (https://gitlab.com/ultsi-projects/blakkisvuohi). It is maintained by @klusteri. Use /terms for the Terms of Service. The privacy policy is in /start, Help, Yksityisyys.",
        },
        "admin_loglevel": {
            "cmd_description": "/loglevel &lt;system|commands|db&gt; &lt;debug|info|error&gt; - säädä logauksen määrää.",
            "level_set_text": "Asetettu '{logger}' tasoksi '{level}'",
        },
        "admin_purge": {
            "cmd_description": "/admin_purge - poista vanhentuneet tiedot heti.",
            "report": "Siivous valmis ({seconds}s): tarkistettu {scanned} tunnusta, poistettu {accounts} tunnusta, {drinks} juomaa ja {leftovers} jäännöstä.",
        },
        "admin_stats": {
            "cmd_description": "/admin_stats - listaa botin statsit",
            "stats_text": "Tilastoja:\nKäyttäjiä on yhteensä {usersCount}kpl, joista vuorokauden sisällä aktiivisia {activeUsers1DayCount}, ja 7pv sisällä aktiivisia {activeUsers7DaysCount}.\nRyhmiä on yhteensä {groupsCount}kpl. Tällä hetkellä tallessa on {drinksNowCount} juomaa, ja kaikki käyttäjät ovat yhteensä tilastoineet {global_drinks_count} juomaa.\nTop10 tilastot:\n\n{top10List}",
            "error": "Virhe! Tilastoja ei saatavilla.",
        },
        "annokset": {
            "cmd_description": "/annokset - kertoo ryhmän kulutetut annokset viimeisen 48h ajalta",
            "text_group": "{chat_title} -käyttäjien rippitaso:\nKäyttäjä...annoksia (yht. 12h/24h)\n\n{list}",
            "text_group_list_item": "{username}... {standard_drinks}kpl ({drinks12h}/{drinks24h})",
        },
        "data": {
            "cmd_description": "/data - lataa omat tiedot talteen.",
            "reply": "Tässä kaikki sinun käyttäjätunnukseen liitetyt tiedot.",
            "no_data": "Sinun käyttäjätunnuksella ei ole tallennettu yhtään tietoa.",
        },
        "start": {
            "on_select": "Veressäsi on {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Olet selvinpäin {hours}h {minutes}min päästä.{drink_list}",
            "on_select_nonuser": "KakkosVuohi korvaa BläkkisVuohen. Vanhan botin tunnukset ja tiedot eivät siirtyneet, joten luo uusi tunnus.\n\nKakkosVuohi auttaa sinua ja ystäviäsi seuraamaan rippauksesi (lue: promillejesi) tasoa. Luo ensimmäiseksi tunnus valitsemalla Luo tunnus. Tunnuksen luomisen jälkeen voit alkaa kellottamaan juomia sisään juomavalikosta. Annan sinulle arvioita rippauksesta promillejen muodossa. Minut voi myös lisätä ryhmään, jolloin kerron /promillet-komennolla kaikkien ryhmässä olevien rippitasot. Jokaisen ryhmäläisen täytyy kuitenkin sanoa ryhmässä /moro, jotta he pääsevät rippilistaukseen mukaan.",
            "header_user": "🐐 <b>Bäää - {title}</b> 🐐\n\n<b>Nyt:</b> {permilles}‰ - <b>30min:</b> {permilles30Min}‰\n\n",
            "header_nonuser": "🐐 <b>Bäää - {title}</b> 🐐\n\n",
            "header_title": "KakkosVuohi",
            "on_select_drinks3h": "\n\nViimeisen kolmen tunnin tapahtumat:\n{drinkList3h}",
            "juo": {
                "button_text": "🥂 Juo",
                "header": "🐐 <b>Bäää - {title}</b> 🐐\n\n<b>Nyt:</b> {permilles}‰ - <b>30min:</b> {permilles30Min}‰\n{drink_list}\n",
                "header_drinks1h": "<b>Viimeisen tunnin tapahtumat:</b>\n{drinkList1h}\n",
                "header_title": "Juo",
                "on_select": "Valitse juomasi alla olevista valikoista. Jos et löydä etsimääsi, klikkaa <b>Oma juoma</b>. Jos olet unohtanut lisätä juomia, voit lisätä ne takautuvasti valitsemalla <b>Jälkikellotus</b>. Jos lisäsit vahingossa väärän juoman, valitse <b>Kumoa</b>. Kaksi alinta nappia ovat pikavalinnat kahdelle viimeisimmälle juomalle.",
                "on_drink": "{drink_response}\n\nJuoma tallennettu.",
                "miedot": {
                    "button_text": "🍻 Miedot",
                    "header_title": "Miedot",
                    "on_select": "Valitse mieto.",
                },
                "viinit": {
                    "button_text": "🍷 Viinit",
                    "header_title": "Viinit",
                    "on_select": "Valitse viini.",
                },
                "shotit": {
                    "button_text": "🥃 Shotit",
                    "header_title": "Shotit",
                    "on_select": "Valitse shotti.",
                },
                "oma": {
                    "button_text": "📝 Oma juoma",
                    "header_title": "Oma juoma",
                    "on_select": "Tilastoi oma juomasi. {help_example}",
                    "help_example": "Kirjoita juoma muodossa senttilitrat prosentit.\nEsim.\n33cl 5.1%, tai 33 5.1",
                    "error_words": "Liian paljon tai vähän sanoja. {help_example}",
                    "error_cl": "Senttilitrat ei ole numero. {help_example}",
                    "error_vol": "Prosentti ei ole numero. {help_example}",
                    "error_exceeds": "Absoluuttisen alkoholin määrä on liian suuri. Tarkista numerot.",
                },
                "jalkikellotus": {
                    "too_many_drinks": "Liian monta juomaa kerralla. Tallenna juomat painamalla Tallenna.",
                    "button_text": "⏱ Jälkikellotus",
                    "header_title": "Jälkikellotus",
                    "on_select": "Jälkikellottamalla voit tilastoida unohtuneet juomat monta tuntia jälkikäteen.\n\nKuinka pitkältä aikaväliltä haluat syöttää unohtuneita juomia? Syötä aikaväli tunneissa.\n\nEsimerkiksi kaksi ja puoli tuntia: <b>2.5</b>\nYksi tunti ja 15 minuuttia: <b>1.25</b>",
                    "hours_error": "Tunnit väärin. Syötä arvo väliltä 0-24.",
                    "input_drinks_start": "Kirjoita juomia seuraavassa muodossa: \nSenttilitrat Tilavuusprosentti. \nEsimerkiksi: 33 4.7. \n\nErota eri juomat joko rivinvaihdolla, tai kirjoita useampi viesti.",
                    "input_drinks_words_error": "Sanojen määrän täytyy olla parillinen luku.",
                    "input_drinks_drink_error": "Tarkista juoman {drink} senttilitrat ja tilavuusprosentti!",
                    "error_out_of_limits": "Tarkista juoman {drink} senttilitrat ja tilavuus, nyt alkoholin määrä ylittää rajat!",
                    "input_drinks_drinks_correct": "{drinks_amount} juoma(a) syötetty onnistuneesti. Voit jatkaa juomien lisäämistä tai painaa Tallenna tilastoidaksesi syötetyt juomat.\n\nNykyiset syötetyt juomat:\n{drinks_list}",
                    "drink_name": "Jälkikellotus",
                    "save": {
                        "button_text": "💾 Tallenna",
                        "on_select": "{drink_response} {drinks_amount} juomaa jälkikellotettu onnistuneesti!\n\n{short_permilles_text}",
                    },
                },
                "kumoa": {
                    "button_text": "❌ Kumoa",
                    "header_title": "Kumoa",
                    "on_select": "Olet kumoamassa viimeksi juodun juomasi. Oletko varma?\n\nKumottava juoma:\n<b>Nimi:</b> {last_drink_name}\n<b>Juotu:</b> {last_drink_created}",
                    "on_select_no_drinks": "Ei kumottavia juomia.",
                    "success": "Kumoaminen onnistui. Olet enää nyt <b>{permilles}‰</b> humalassa ja 30min päästä <b>{permilles30Min}‰</b> humalassa.",
                },
            },
            "asetukset": {
                "button_text": "⚙ Asetukset",
                "on_select": "Asetuksista voit muokata tunnustasi tai poistaa tunnuksesi.",
                "header": "🐐 <b>Bäää - {title}</b> 🐐\n\n",
                "header_title": "Asetukset",
                "muokkaa": {
                    "button_text": "👤 Muokkaa tunnusta",
                    "on_select": "Voit muokata tässä tunnuksesi painoa, pituutta ja sukupuolta sekä päivittää nimimerkin.\n\nNykyiset tiedot:\n<b>Nimimerkki:</b> {username}\n<b>Paino:</b> {weight}kg\n<b>Pituus:</b> {height}cm\n<b>Sukupuoli:</b> {gender}\n<b>ID:</b> {user_id}",
                    "paino": {
                        "button_text": "⚖ Muokkaa painoa",
                        "on_select": "<b>Paino nyt:</b> {weight}kg\n\nSyötä uusi painosi kokonaislukuna.",
                        "on_change": "Paino muutettu!",
                    },
                    "pituus": {
                        "button_text": "📏 Muokkaa pituutta",
                        "on_select": "<b>Pituus nyt:</b> {height}cm\n\nSyötä uusi pituutesi kokonaislukuna.",
                        "on_change": "Pituus muutettu!",
                    },
                    "sukupuoli": {
                        "button_text": "♀♂ Muokkaa sukupuolta",
                        "on_select": "<b>Sukupuoli nyt:</b> {gender}\n\nValitse uusi biologinen sukupuolesi alta:",
                        "on_change": "Sukupuoli muutettu!",
                    },
                },
                "poista": {
                    "button_text": "🗑 Poista tunnus",
                    "on_select": "Olet poistamassa tunnuksesi. Hyväksymällä poistat kaiken sinuun liittyvän tiedon KakkosVuohen tietokannoista eikä sinua enää ole mahdollista listata missään listauksissa.\n\nOletko varma, että haluat poistaa tunnuksesi?",
                    "double_confirm": "Oletko aivan varma? Kaikki tietosi <b>poistetaan</b> jos klikkaat kyllä.",
                    "canceled": "Peruit tunnuksen poistamisen.",
                    "deleted": "Kaikki tietosi on nyt poistettu. Rippaa rauhassa.",
                },
                "paivita": {
                    "button_text": "🔃 Päivitä nimi",
                    "on_select": "Nimi päivitetty! Nimesi on nyt: <b>{username}</b>. Voit päivittää nimeäsi vaihtamalla sen ensiksi Telegramin asetuksista, ja sen jälkeen päivittämällä sen tällä komennolla.",
                },
            },
            "luo_tunnus": {
                "button_text": "🌟 Luo tunnus",
                "header_title": "Luo tunnus",
                "on_select": "Tarvitset tunnusta käyttääksesi suurinta osaa botin ominaisuuksista. Aloita tunnuksen luominen syöttämällä painosi kilogrammoissa ja kokonaislukuna:",
                "weight_error": "Syötä paino uudelleen. Painon pitää olla kokonaisluku ja ala- ja ylärajat ovat 20kg ja 250kg.",
                "height": "Paino syötetty. Syötä seuraavaksi pituus senttimetreissä:",
                "height_error": "Syötä pituus uudelleen. Pituuden täytyy olla kokonaisluku ja ala- ja ylärajat ovat 120cm ja 240cm.",
                "gender": "Pituus syötetty. Syötä seuraavaksi biologinen sukupuoli:",
                "gender_error": "Syötä joko mies tai nainen:",
                "terms": "Sukupuoli syötetty. \n\n{terms}\n\nOletko lukenut ja hyväksynyt käyttöehdot?",
                "terms_answer_yes": "Kyllä",
                "terms_answer_no": "En",
                "terms_on_reject": "Lue käyttöehdot ja hyväksy ne, ennen kuin voit käyttää muita komentoja.",
                "terms_error": "Oletko lukenut ja hyväksynyt käyttöehdot?",
                "update": "Olet jo rekisteröitynyt. Tiedot päivitetty.",
                "update_error": "Olet jo rekisteröitynyt, mutta tietojen päivityksessä tuli ongelma. Ota yhteyttä adminiin.",
                "new_user": "Moikka {username}! Tunnuksesi luotiin onnistuneesti. Muista, että kaikki antamani luvut ovat vain arvioita, eikä niihin voi täysin luottaa.\n\nJa eikun juomaan!",
            },
            "tilastoja": {
                "button_text": "📊 Tilastoja",
                "header_title": "Tilastoja",
                "on_select": "Valitse tarkasteltava tilasto alla olevista valikoista. <b>Kulutus</b> kertoo sinulle kokonaiskulutuksestasi lukuja ja <b>Otinko</b> listaa viimeisen 3 päivän aikana tilastoidut juomat.",
                "kulutus": {
                    "button_text": "Kulutus",
                    "on_select": "Olet <b>{day_count}</b> päivän aikana tuhonnut <b>{grams}</b> grammaa alkoholia, joka vastaa <b>{standard_drinks}</b> annosta. Keskimäärin olet juonut <b>{avg_standard_drinks}</b> annosta per päivä.\n\nJos haluat tietää lähiajan kulutuksesi, kirjoita tarkasteltavien päivien määrä numerona.",
                    "prefilled": "Olet <b>{day_count}</b> päivän aikana tuhonnut <b>{grams}</b> grammaa alkoholia, joka vastaa <b>{standard_drinks}</b> annosta. Keskimäärin olet juonut <b>{avg_standard_drinks}</b> annosta per päivä.",
                    "days7": "7 päivää",
                    "days14": "14 päivää",
                    "days30": "30 päivää",
                    "days60": "60 päivää",
                },
                "otinko": {
                    "button_text": "Otinko",
                    "on_select": "Viimeisen kolmen vuorokauden tapahtumat:\n\n{drink_list}",
                },
            },
            "help": {
                "button_text": "ℹ Help",
                "header": "🐐 <b>Bäää - {title}</b> 🐐\n\n",
                "header_title": "Help",
                "on_select": "Missä tarvitset apua?",
                "general": {
                    "button_text": "Yleistä",
                    "header_title": "Help: Yleistä",
                    "on_select": "KakkosVuohi auttaa arvioimaan alkoholin määrää veressä eli promilleja. Botille tilastoidaan juomia sitä mukaa, kun niitä juodaan, ja botti laskee juoduista juomista promillet, palamisen huomioon ottaen. Lisäksi botin voi lisätä ryhmään ryhmätilastoja varten.\n\n<b>Käyttö</b>\n\nBotin käyttäminen on yksinkertaista. Juodut juomat tilastoidaan joko /juoma- tai /start- komentoja käyttäen ja botti laskee promillemäärän heti. Botin käyttö <b>vaatii tunnuksen</b> luomisen, jonka voi tehdä joko /tunnus- tai /start- komennoilla. Tunnus vaaditaan, jotta promillejen arviointi olisi mahdollisimman tarkkaa.",
                },
                "faq": {
                    "button_text": "FAQ",
                    "header_title": "FAQ",
                    "on_select": "Valitse yksi ala-aiheista:",
                    "juominen": {
                        "button_text": "Juominen",
                        "header_title": "FAQ: Juominen",
                        "on_select": "<b>Kannattaako juoma merkata avatessa vai viimeistellessä?</b>\nJuomat kannattaa merkata silloin, kun ne avaa. Promillearvioinnissa oletetaan juoman imeytyvän 99-prosenttisesti 30 minuutissa. Lisäksi avatessa juoman muistaa merkata paremmin.\n\n<b>Kuinka tarkka promillejen arviointi on?</b>\nNoin 1.5‰ asti hyvin tarkka - tätä pidemmälle menneitä tutkimuksia ei ole tehty (jos on, laita viestiä @klusteri), joten laskukaava alkaa heittämään 1.5‰ jälkeen. Botin arviot ovat myös linjassa mm. lintukoto.net -laskurin kanssa.\n\n<b>Unohdin lisätä juomat, mitä nyt?</b>\nKäytä /jalkikellotus-komentoa, tai /start-valikosta löytyvää Jälkikellotus-nappulaa.",
                    },
                    "ryhmat": {
                        "button_text": "Ryhmät",
                        "header_title": "FAQ: Ryhmät",
                        "on_select": '<b>Miten voin liittyä ryhmään tai poistua ryhmästä?</b>\nKirjoita /moro, jos haluat liittyä ryhmään. Kirjoita /poistu, jos haluat poistua ryhmästä. Ryhmään liittyneenä sinun promilletasosi näkyy esim. /promillet-komennolla.\n\n<b>Miksi /kuvaaja -kuvassa kaikkien promillet laskee samaa tahtia?</b>\nPromillet kuvaavat alkoholin osuutta koko kehon verestä. Alkoholi palaa elimistössä nopeammin painavammilla ihmisillä, mutta veren määrä kehossa on tällöin myös suhteessa noin saman verran korkeampi. Tällöin promillejen väheneminen kehossa on kaikilla ihmisillä jotakuinkin sama.\n\n<b>Tallentaako KakkosVuohi ryhmän viestit?</b>\n<b>Ei tallenna.</b> Jos menet ryhmän käyttäjälistaukseen, KakkosVuohen kohdalla lukee "No access to messages", joka tarkoittaa, ettei KakkosVuohi voi millään tavalla lukea muita viestejä kuin komentoja.',
                    },
                    "koodi": {
                        "button_text": "Koodi",
                        "header_title": "FAQ: Koodi",
                        "on_select": "<b>Miten KakkosVuohi on koodattu?</b>\nLyhyesti: Python-kielellä aiogram-kirjastoa käyttäen, ja tietokantana toimii SQLite. Koko koodi on osoitteessa https://github.com/antoKeinanen/KakkosVuohi.\n\n<b>Keksin uuden ominaisuuden, minne voin ilmoittaa siitä?</b>\nLaita viestiä @klusteri tai avaa issue GitHubissa: https://github.com/antoKeinanen/KakkosVuohi/issues\n\n",
                    },
                },
                "privacy": {
                    "button_text": "Yksityisyys",
                    "header_title": "Help: Yksityisyys",
                    "where_server": "Tietoja säilytetään botin ylläpitäjän palvelimella, ja vain ylläpitäjällä on sinne pääsy.",
                    "where_workers": "Tietoja säilytetään Cloudflaren palvelussa (Workers ja D1), ja vain botin ylläpitäjällä on niihin pääsy.",
                    "history_workers": " Cloudflare säilyttää tietokannoista palautettavaa historiaa enintään 30 päivää, joten ylläpitäjä voisi vielä sen ajan palauttaa poistetut tiedot. Keskeneräisten komentojen tiedot (esim. tunnusta luodessa syötetyt mitat) tallennetaan salattuina ja poistetaan viimeistään kahden päivän kuluttua.",
                    "on_select": "Tässä kerrotaan, mitä tietoja KakkosVuohi tallentaa ja miten niitä suojataan.\n\n<b>Mitä tietoja kerätään?</b>\nKakkosVuohen käyttö edellyttää seuraavien tietojen keräämistä:\n- Telegramiin määritelty nimimerkki tai nimi\n- Salaisella avaimella laskettu tiiviste (HMAC) Telegram-tilisi tunnisteesta (userId)\n- Paino ja pituus (tallennetaan pyöristettynä lähimpään viiteen)\n- Sukupuoli\n- Merkattujen juomien alkoholipitoisuudet, nimet ja juomisajat\n- Salaisella avaimella lasketut tiivisteet (HMAC) liityttyjen ryhmien tunnisteista (groupId)\n- Päivä, jona viimeksi käytit KakkosVuohta\n\n<b>Kuinka kauan tietoja säilytetään?</b>\nJuomat poistetaan automaattisesti {retention_days} päivän jälkeen, ja tunnus kaikkine tietoineen poistetaan, jos et käytä KakkosVuohta {account_days} päivään. Siivous tehdään joka päivä.\n\n<b>Missä ja miten tietoja säilötään?</b>\n{where} Kaikki sinuun liittyvät tiedot (nimimerkki, mitat, juomat) on salattu tietokannassa (AES-256-GCM) omalla avaimellasi, ja avaimet säilytetään erillään tiedoista. Tunnuksen poistaminen tuhoaa avaimesi, jolloin tiedot eivät ole luettavissa enää mistään.{history} Voit ladata kaikki tietosi komennolla /data ja poistaa ne asetuksista.\n\n<b>Minulla on lisäkysymyksiä yksityisyyteen liittyen!</b>\nOta yhteyttä @klusteri.",
                },
            },
        },
        "help": {"cmd_description": "/help - tulosta ohje"},
        "komennot": {"cmd_description": "/komennot - listaa kaikki botin komennot"},
        "jalkikellotus": {
            "too_many_drinks": "Liian monta juomaa kerralla. Kirjoita stop tallentaaksesi juomat.",
            "cmd_description": "/jalkikellotus - Kellota unohtuneet juomat mukaan tilastoihin",
            "start": "Kuinka pitkältä aikaväliltä haluat syöttää unohtuneita juomia? Syötä aikaväli tunneissa. \n\nEsimerkiksi kaksi ja puoli tuntia: 2.5 \nYksi tunti ja 15 minuuttia: 1.25.",
            "hours_error": "Tunnit väärin. Mahdolliset arvot välillä 0-24.",
            "input_drinks_start": "Kirjoita juomia seuraavassa muodossa: \nSenttilitrat Tilavuusprosentti. \nEsimerkiksi: 33 4.7. \n\nErota eri juomat joko rivinvaihdolla, tai kirjoita useampi viesti. Lopeta ja tallenna juomat kirjoittamalla stop.",
            "input_drinks_error": "Kirjoititko varmasti ohjeiden mukaisesti?",
            "input_drinks_drink_error": "Tarkista juoman {drink} senttilitrat ja tilavuus!",
            "error_out_of_limits": "Tarkista juoman {drink} senttilitrat ja tilavuus, nyt alkoholin määrä ylittää rajat!",
            "input_drinks_drink_saved": "Juoma tallennettu!",
            "drink_name": "Jälkikellotus",
        },
        "juoma": {
            "cmd_description": "/juoma - lisää yksi juoma tilastoihin",
            "start": "Valitse juoman kategoria",
            "start_error": "Virhe! Valitse yksi kategorioista",
            "to_start": "Alkuun",
            "milds": "Miedot",
            "booze": "Tiukat",
            "self_define": "Oma",
            "choose_mild": "Valitse mieto",
            "choose_booze": "Valitse tiukka",
            "self_define_vol": "Syötä juoman tilavuusprosentti numerona. Esim: 12.5 (viini), 5.5 (lonkero), 60 (absintti)",
            "self_define_cl": "Syötä juoman määrä senttilitroissa numerona. Esim: 4 (shotti), 33 (tölkki), 70 (viinipullo)",
            "self_define_error_alcohol_limit": "Absoluuttisen alkoholin määrä on liian suuri. Aloita uusiksi",
        },
        "kalja033": {
            "cmd_description": "/kalja033 - pikanäppäin yhdelle kappaleelle olutta. Ammattilaiskäyttöön."
        },
        "kalja05": {
            "cmd_description": "/kalja05 - pikanäppäin yhdelle kappaleelle 0.5l olutta. Ammattilaiskäyttöön."
        },
        "kuvaaja": {
            "cmd_description": "/kuvaaja - Näyttää ryhmän 24h tapahtumat kuvaajana.",
            "graph_title": "Promillekuvaaja feat. {chat_title}",
            "img_failed": "Kuvan muodostus epäonnistui!",
        },
        "laatta": {
            "cmd_description": "/laatta - Poista viimeksi merkattu juoma tilastoista.",
            "start_text": "Olet laattaamassa viimeksi juodun juomasi. Oletko varma?",
            "start_answer_yes": "Kyllä",
            "start_answer_no": "En",
            "error_text": "Kirjoita kyllä tai en.",
            "success": "Laatta onnistui. Olet enää nyt {permilles}‰ humalassa ja 30min päästä {permilles30Min}‰ humalassa.",
            "cancel": "Laatta peruttu.",
        },
        "moro": {
            "cmd_description": "/moro - Lisää sinut ryhmään mukaan.",
            "join_text": "Rippaa rauhassa kera {chat_title} -kavereiden.",
        },
        "poistu": {
            "cmd_description": "/poistu - Poistu ryhmästä.",
            "leave_text": "Ei enää rippausta kera {chat_title} -kavereiden.",
        },
        "promillet": {
            "cmd_description": "/promillet - näytä sinun tai ryhmän promillet. Yksityisviestinä käytettynä listaa myös viimeisen 3pv tapahtumat.",
            "text_group": "{chat_title} -käyttäjien rippitaso:\nKäyttäjä...‰ (annoksia 12h/24h)\n\n{list}",
            "text_group_list_item": "{username}... {permilles} ({drinks12h}/{drinks24h})",
        },
        "stats": {
            "cmd_description": "/stats - listaa ryhmän tai sinun kulutustilastoja. Lisäämällä numeron komennon perään voit valita, kuinka monelta päivältä taaksepäin haluat tilastot. Tilastot kattavat enintään tietojen säilytysajan",
            "private": "Olet {day_count} päivän aikana tuhonnut {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Keskimäärin olet juonut {avg_standard_drinks} annosta per päivä.",
            "group": "Tilastoja:\n\nRyhmän jäsenet ovat {day_count} päivän aikana tuhonneet {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Keskimäärin on juotu {avg_standard_drinks} annosta per päivä. Lisäksi kaikki käyttäjät globaalisti ovat yhteensä tilastoineet {global_drinks_count} juomaa. Hienosti.\n\nTop10 tilastot <b>juomina</b>:\n\n{top10List}",
        },
        "stats2": {
            "cmd_description": "/stats2 - listaa ryhmän tai sinun kulutustilastoja annoksittain. Lisäämällä numeron komennon perään voit valita, kuinka monelta päivältä taaksepäin haluat tilastot. Tilastot kattavat enintään tietojen säilytysajan",
            "private": "Olet {day_count} päivän aikana tuhonnut {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Keskimäärin olet juonut {avg_standard_drinks} annosta per päivä.",
            "group": "Tilastoja:\n\nRyhmän jäsenet ovat {day_count} päivän aikana tuhonneet {grams} grammaa alkoholia, joka vastaa {standard_drinks} annosta. Keskimäärin on juotu {avg_standard_drinks} annosta per päivä. Lisäksi kaikki käyttäjät globaalisti ovat yhteensä tilastoineet {global_drinks_std} annosta. Hienosti.\n\nTop10 tilastot <b>annoksina</b>:\n\n{top10List}",
        },
        "terms": {
            "cmd_description": "/terms - Terms of Service",
            "reply": "<b>Käyttöehdot</b>\n\nKäyttämällä KakkosVuohta olet hyväksynyt seuraavat käyttöehdot. KakkosVuohen päätarkoitus on arvioida alkoholin määrää kehossa. KakkosVuohen toiminta voi muuttua tai pysähtyä milloin vain. Sinun täytyy olla yli 18 vuotta käyttääksesi KakkosVuohta. KakkosVuohen kehittäjät tai ylläpitäjät eivät ole vastuussa mistään suorasta tai epäsuorasta haitasta, jota palvelun käyttäminen voi aiheuttaa. KakkosVuohi on ilmainen käyttää. Ominaisuuksien, kuten promillejen arvioiminen, takia KakkosVuohi tallentaa käyttäjistä erinäisiä tietoja ja käyttää näitä hyväksi laskennassa. Sinuun suoraan linkitettävät tiedot salataan ennen tallentamista. Tietoja ei koskaan anneta tai myydä eteenpäin kolmansille osapuolille. Tiedot poistetaan automaattisesti määräajan jälkeen (katso /start, Help, Yksityisyys), ja voit poistaa ne itse milloin vain asetuksista.\n\nKakkosVuohen tuottamat arviot ovat arvioita, eikä niihin voi missään tapauksessa täysin luottaa. Noudata lakia, kun käytät alkoholia.\n\nNämä käyttöehdot voivat muuttua milloin vain ilman erillistä huomautusta. Uusimmat käyttöehdot voi aina lukea /terms-komennolla. Nämä käyttöehdot ovat voimassa 14.11.2026 lähtien.",
        },
        "tunnus": {
            "cmd_description": "/tunnus - Luo itsellesi uusi tunnus tai muokkaa tunnustasi.",
            "start": "Tervetuloa tunnuksen luomiseen tai päivittämiseen. Alkoholilaskuria varten tarvitsen seuraavat tiedot: paino, pituus ja sukupuoli.\n\nSyötä ensimmäiseksi paino kilogrammoissa ja kokonaislukuna:",
            "start_error": "Syötä paino uudelleen. Painon pitää olla kokonaisluku ja ala- ja ylärajat ovat 20kg ja 250kg.",
            "height": "Paino tallennettu. Syötä seuraavaksi pituus senttimetreissä:",
            "height_error": "Syötä pituus uudelleen. Pituuden täytyy olla kokonaisluku ja ala- ja ylärajat ovat 120cm ja 240cm.",
            "gender": "Pituus tallennettu. Syötä seuraavaksi sukupuoli:",
            "gender_error": "Syötä joko mies tai nainen:",
            "terms": "Sukupuoli tallennettu. \n\n{terms}\n\nOletko lukenut ja hyväksynyt käyttöehdot?",
            "terms_answer_yes": "Kyllä",
            "terms_answer_no": "En",
            "terms_on_reject": "Lue käyttöehdot ja hyväksy ne, ennen kuin voit käyttää muita komentoja.",
            "terms_error": "Oletko lukenut ja hyväksynyt käyttöehdot?",
            "update": "Olet jo rekisteröitynyt. Tiedot päivitetty.",
            "update_error": "Olet jo rekisteröitynyt, mutta tietojen päivityksessä tuli ongelma. Ota yhteyttä adminiin.",
            "new_user": "Moikka {username}! Tunnuksesi luotiin onnistuneesti. Muista, että kaikki antamani luvut ovat vain arvioita, eikä niihin voi täysin luottaa. Ja eikun juomaan!",
        },
        "whoami": {
            "cmd_description": "/whoami - tulosta omat tietosi.",
            "reply": "Käyttäjä {username}\nID: {user_id}\nPaino: {weight}kg\nPituus: {height}cm\nSukupuoli: {gender}",
        },
    },
}

S = _ns(_STRINGS)
