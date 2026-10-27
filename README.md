# Event Dimension – pubblicazione automatica Instagram

Pubblica da solo post, carousel e storie su **@eventdimension_experience**
all'orario previsto, senza abbonamenti.

## Come funziona
- `calendar.csv` – il calendario: una riga per contenuto.
- `media/` – le immagini **JPG** (servite pubblicamente da GitHub Pages).
- Ogni 10 minuti GitHub Actions avvia `publish.py`: pubblica le righe arrivate
  all'orario e aggiorna la colonna `status`.
- Ogni lunedì il token Instagram viene rinnovato da solo.

## Il calendario (`calendar.csv`)
| colonna | cosa contiene |
|---|---|
| id | codice univoco |
| datetime | `AAAA-MM-GG HH:MM`, ora italiana |
| type | `POST`, `CAROUSEL`, `REEL` (video MP4, eventuale copertina JPG come secondo file), `STORY` (pubblicati in automatico) oppure `REMINDER` (notifica sul telefono con immagine e link, per storie/reel da pubblicare a mano) |
| media | nome del file in `media/` (per il carousel più file separati da `\|`) |
| caption | testo del post (le storie non hanno testo) |
| status | `scheduled` → poi `published`, `queued` (promemoria già affidato a ntfy con consegna all'ora esatta), `error` o `skipped` |
| result / note | ID Instagram o messaggio di errore |

Se un contenuto non riesce a partire entro 6 ore dall'orario viene segnato `skipped`.

## Secrets necessari (Settings → Secrets and variables → Actions)
- `IG_TOKEN` – token Instagram (long-lived)
- `IG_USER_ID` – ID dell'account Instagram
- `NTFY_TOPIC` – nome del canale ntfy su cui arrivano le notifiche
- `GH_PAT` – token GitHub con permesso "Secrets: read and write" su questo repository
  (serve solo per salvare il token rinnovato)

## Limiti
- Instagram accetta solo immagini JPG.
- Gli sticker delle storie (link, sondaggi, conto alla rovescia) non si possono
  aggiungere via API: vanno messi a mano dall'app.
- GitHub può avviare i controlli con qualche minuto di ritardo (fino a ~30): i POST possono uscire un po' dopo l'orario.
  I promemoria invece arrivano puntuali, perché vengono consegnati da ntfy all'ora esatta (fino a 60 ore prima vengono già messi in coda).
- Un promemoria in stato `queued` non si può più modificare dal calendario.
