# isel-cnc mit Marlin: Bearbeitungsprotokoll vom 17.11.2026

Dieses Protokoll dokumentiert zwei ausgeführte Operationen: vier Konturausschnitte aus einer DXF und das schrittweise Abfräsen einer über zwei Punkte definierten Kante. Es ist keine unmittelbar ausführbare Arbeitsanweisung. Koordinaten gelten nur für die damalige Aufspannung und Werkzeugreferenz.

## Maschine und Verbindung

| Merkmal | Verwendeter Stand |
| --- | --- |
| Maschine | isel-cnc, Marlin / RAMPS 1.4 laut Projektaufbau |
| Firmwareantwort | Marlin bugfix-2.1.x, kompiliert am 19.02.2024 |
| USB-Seriell | CH340, COM3, 250000 Baud |
| Bedienung | `app.py`, Flask und pyserial; lokale Weboberfläche auf `http://localhost:5000` |
| Server dieser Sitzung | Auf 127.0.0.1, ohne Debugger und automatischen Reload gestartet |
| Software-Endschalter | Aktiv; X 0–300, Y 0–230, Z 0–85 mm |
| Endschaltereingänge | X-Min, Y-Max, Z-Max |
| Vollständiges Homing | `G28`, einschließlich Z; bestätigte Endanzeige X 0 / Y 230 / Z 85 |
| Spindel | Manuell eingeschaltet und eingestellt; nicht automatisch am Jobende ausgeschaltet |

Alle Positionswerte unten sind die in dieser Sitzung von Marlin gemeldeten Koordinaten in mm. Nach einem Neustart meldete Marlin ebenfalls X 0 / Y 230 / Z 85, obwohl die Achsen physisch anders standen. Diese Startanzeige war **kein Nachweis eines erfolgten Homings**.

Die Befehle wurden über die HTTP-Endpunkte der vorhandenen Anwendung gesendet. Ein separater Sender wartete auf Controllerantworten; `M400` bestätigte das Ende der geplanten Bewegung vor Phasenwechseln. Ein HTTP-Erfolg allein bestätigt nur das Senden, nicht die ausgeführte Bewegung. Die vorhandene Webanwendung wurde dabei nicht erweitert.

## Operation 1: Vier Konturausschnitte

### Zeichnung und ursprünglicher Bezug

- Lokale Quelle: `D:\gcode\26-11-17_1203_conn_cut.dxf`.
- Einheit: mm; vier geschlossene Polylinien mit Eckbögen und Freistellungen.
- Die Konturen sind in Y jeweils um 58 mm versetzt; die X-Geometrie ist identisch.
- Material laut Benutzer: PVC, 2 mm dick, mit Opferplatte darunter.
- Zieltiefe: 2,4 mm unter der Werkstückoberfläche, also nominell 0,4 mm in die Opferplatte.
- Acht umlaufende Rampen mit jeweils 0,3 mm Zustellung, anschließend eine volle Runde auf Endtiefe. Die 0,3 mm wurden entlang einer ganzen Konturrunde zugestellt, nicht senkrecht an einem Punkt.

Der Benutzer stellte die Fräsermitte auf die Mitte der oberen geraden Bahn der obersten Kontur. Der gespeicherte Ausgangspunkt war **X 130,00 / Y 228,00 / Z 21,10**. Z 21,10 wurde anschließend ausdrücklich als Materialoberfläche bestätigt.

Für die damalige DXF-Zuordnung lag dieser Bezug bei ungefähr X −0,038460 / Y −80,564644 in der Zeichnung. Die Translation betrug X +130,038460 / Y +308,564644.

### Erster Lauf mit Ø 1,5 mm

| Parameter | Wert |
| --- | --- |
| Fräser | Ø 1,5 mm, vier Schneiden |
| Spindeldrehzahl | 8000 U/min eingestellt und laufend bestätigt |
| XY-Vorschub beim Fräsen | 400 mm/min |
| Zustellung | 0,3 mm je Umlauframpe, insgesamt −2,4 mm |
| Oberfläche / Endtiefe | Z 21,10 / Z 18,70 |
| Sicherheitshöhe | Z 46,10, also Oberfläche +25 mm |
| Probefahrt | Obere Kontur mit 300 mm/min auf Sicherheitshöhe |

Bei diesem ersten Lauf folgte die **Fräsermitte direkt der DXF-Kontur**, ohne Radiuskorrektur. Die Zeichnung wurde damit als Bahn interpretiert, nicht als bereits kompensierte Fertigkante. Die resultierende Schnittkante ist um den Werkzeugradius gegenüber der gezeichneten Bahn versetzt.

Die Eckbögen der oberen Kontur reichten bis Y 228,3661, also 0,3661 mm über den geraden oberen Bezug hinaus. Zur Softwaregrenze Y 230 blieben für die Fräsermitte 1,6339 mm. Alle vier programmierten Konturen lagen innerhalb der Softwaregrenzen; das prüft keine Spannmittel oder Werkzeughalter.

**Unterbrechung:** Taschen 1 und 2 wurden einschließlich Endrunde fertig gefahren. Tasche 3 wurde in der sechsten Umlauframpe unterbrochen. Die letzte bestätigte Bahnposition war X 109,3343 / Y 112,2942 / Z 19,5633; der nächste gesendete Punkt X 109,2062 / Y 112,2406 / Z 19,5630 erhielt kein `ok`. Tasche 4 war zu diesem Zeitpunkt unbearbeitet.

### Verbindungsabbruch und fehlgeschlagene Wiederherstellung

- Windows protokollierte Modern Standby wegen Inaktivität um 11:13:50 und das Aufwachen um 11:20:54. Die letzte Controllerantwort vor dem Ausfall war um 11:18:02. Das stützt Energiesparen als Ursache; ein anderer USB- oder Controllerfehler wurde nicht ausgeschlossen.
- COM3 blieb im Geräte-Manager sichtbar, während der serielle Zugriff später mit „Zugriff verweigert“ scheiterte. Auch der gesendete Schnellstopp `M410` wurde zunächst nicht bestätigt.
- Erneutes Öffnen von COM3 setzte Marlin zurück. Die bisherigen Istkoordinaten gingen verloren.
- Ein getrenntes `G28 Z` lieferte `ok`, obwohl der Benutzer anschließend eine fehlgeschlagene tatsächliche Z-Referenzierung meldete. Die nachfolgende X/Y-Fahrt wurde damit auf einer unzureichend geprüften Z-Freigabe begonnen. Das war ein Fehler im Wiederherstellungsablauf.
- Der Benutzer trennte die Maschinenversorgung; später stand im Protokoll `Homing Failed` und `Printer halted`. Der Fräser war bei der Aktion abgebrochen.
- Der Benutzer vermutete außerdem eine Werkstückverschiebung und richtete das Werkstück neu aus. Die vorher beobachtete X-Abweichung von etwa 1 mm wurde deshalb **nicht als dauerhafter Homing- oder Werkstückoffset übernommen**.
- Ein späteres vollständiges `G28` wurde sowohl vom Controller als auch vom Benutzer für die tatsächliche Bewegung aller drei Achsen bestätigt.

Für künftige Referenzierungen ist der Benutzerwunsch: normales vollständiges `G28` einschließlich Z. Nach einem Verbindungsabbruch oder Neustart müssen freie Wege und reale Achsbewegungen geprüft werden; alte Displaywerte oder `ok` allein ersetzen das nicht. Homing stellt den Maschinenbezug wieder her, nicht eine verschobene Aufspannung oder die Werkzeuglänge.

### Fortsetzung mit Ø 2 mm

Die neue Oberfläche wurde mit dem neuen Werkzeug manuell angetastet und als **Z 22,20** gespeichert. Die alte Z-Oberfläche des 1,5-mm-Werkzeugs wurde nicht weiterverwendet.

| Parameter | Wert |
| --- | --- |
| Fräser | Ø 2 mm; Schneidenzahl nicht erneut dokumentiert |
| Spindeldrehzahl | 7500 U/min, laufend bestätigt |
| XY-Vorschub | 400 mm/min |
| Konturprobefahrt | 300 mm/min |
| Z-Anfahrt von oben | 180 mm/min bis 1 mm über Oberfläche, anschließend 60 mm/min bis Oberfläche |
| Oberfläche / Endtiefe | Z 22,20 / Z 19,80 |
| Sicherheitshöhe | Z 47,20 = Oberfläche +25 mm |
| Zustellung | Acht Umlauframpen à 0,3 mm, plus eine Endrunde auf gleicher Tiefe |

Die Radiuszunahme gegenüber dem alten Werkzeug beträgt **(2,0 − 1,5) / 2 = 0,25 mm**. Um die bereits angelegte äußere Schnittbegrenzung zu erhalten, wurde die ursprüngliche Fräsermittelbahn um 0,25 mm **nach innen versetzt**. Das betrifft die ganze Kontur, nicht nur eine Verschiebung aller Y-Werte. Es ist eine Korrektur gegenüber dem alten Werkzeug, keine allgemeine 0,25-mm-Kompensation beliebiger DXF-Fertigkonturen.

Für die Konturkorrektur wurden die DXF-Bögen zuvor mit höchstens etwa 0,002 mm Sehnenfehler abgetastet und die gültige geschlossene Kontur mit Shapely nach innen versetzt.

| Prüf- oder Startpunkt | X | Y |
| --- | ---: | ---: |
| Obere Mitte Tasche 1, kompensiert | 130,0000 | 227,7500 |
| Rechte gerade Innenwand, Fräsermitte | 150,8817 | Prüfpunkt entlang der Wand frei wählbar |
| Linke gerade Innenwand, ursprünglicher Bezug | 109,0817 | Prüfpunkt entlang der Wand frei wählbar |
| Obere Mitte Tasche 3, kompensiert | 130,0000 | 111,7500 |
| Obere Mitte Tasche 4, kompensiert | 130,0000 | 53,7500 |

Die rechte gerade Schnittbegrenzung liegt mit dieser Definition bei etwa X 151,8817; die Fräsermitte des 2-mm-Werkzeugs liegt 1 mm links davon. Ein vorübergehend gemessener Kontakt bei X 149,88 führte nur zu einer relativen Vergleichsfahrt. Nach der Werkstückausrichtung bestätigte der Benutzer den ursprünglichen berechneten rechten Prüfpunkt erneut. Ebenso wurde die vorübergehende Y-Position 228,65 ausdrücklich **nicht** als neuer Y-Bezug übernommen.

Vor der Fortsetzung wurde Tasche 3 vollständig auf **Z 22,60**, also 0,4 mm über der neuen Oberfläche, mit der kompensierten Kontur abgefahren und vom Benutzer bestätigt.

**Ergebnis:** Taschen 3 und 4 wurden mit Ø 2 mm jeweils erneut ab Oberfläche über alle acht Rampen und die Endrunde gefahren. Der Controller bestätigte den Abschluss ohne Fehler. Parkposition danach: **X 130 / Y 111,75 / Z 47,20**. Taschen 1 und 2 wurden nicht mit dem neuen Werkzeug nachgearbeitet.

## Operation 2: Kante über zwei Punkte abfräsen

Für diese Operation wurde das Werkstück neu eingespannt. Die Taschen-Z-Referenz wurde nicht auf die Linie übertragen. Der Benutzer bestätigte an der Kante: Bewegung in −Y entfernt den Fräser vom Material; das Material liegt dort auf der +Y-Seite. Ein weiterer Werkzeugwechsel wurde nicht gemeldet; die Spindel wurde als laufend bestätigt, ihre Drehzahl für diese Operation nicht erneut erfasst.

### Gespeicherte Kontaktpunkte und verlängerte Linie

| Punkt | X | Y | Z |
| --- | ---: | ---: | ---: |
| A, manuell angefahren | 190,1000 | 189,6500 | 27,3000 |
| B, manuell angefahren | 208,8000 | 194,4500 | 26,7000 |
| Verlängerter Anfang S | 185,2570 | 188,4069 | 27,4554 |
| Verlängertes Ende E | 228,1720 | 199,4225 | 26,0784 |

Die XY-Distanz A–B beträgt **19,3062 mm**. Die Linie wurde **5 mm vor A** und zunächst 15 mm, nach einer weiteren Probefahrt schließlich **20 mm hinter B** verlängert. Die endgültige XY-Länge beträgt **44,3062 mm**. Die Verlängerungsmaße wurden entlang der XY-Richtung gemessen.

Berechnung mit `L = Länge(Bxy − Axy)` und `u = (Bxy − Axy) / L`:

- `Sxy = Axy − 5 · u`
- `Exy = Bxy + 20 · u`
- `Z(s) = ZA + s · (ZB − ZA) / L`, mit s als vorzeichenbehafteter XY-Strecke ab A.

Damit werden die um 0,60 mm unterschiedlichen Z-Werte an A und B linear interpoliert und an den verlängerten Enden extrapoliert. Die gespeicherten Z-Werte waren manuell angefahrene Kontaktwerte, keine unabhängig vermessene Oberflächenkarte.

### Probe und Schnittdurchgänge

1. Probefahrt der verlängerten XY-Linie auf konstant **Z 46,70**, entsprechend **Z an B +20 mm**. Diese Probefahrt enthielt noch keinen geneigten Z-Verlauf.
2. Eine Kontaktfahrt mit dem oben berechneten linearen XYZ-Verlauf und ohne zusätzliche Zustellung. Vorschub 150 mm/min; der Benutzer bestätigte das Ergebnis.
3. Vierzehn weitere Durchgänge mit jeweils **+0,10 mm zusätzlichem Y-Versatz** gegenüber dem vorherigen Schnitt. Der Gesamtversatz wurde bis **+1,40 mm** aufgebaut.

| Schnittdurchgänge | Gesamter Y-Versatz zur Kontaktlinie | Z-Versatz zur Kontaktlinie |
| --- | --- | --- |
| 1–2 | +0,10 und +0,20 mm | 0,00 mm |
| 3–14 | +0,30 bis +1,40 mm, in 0,10-mm-Schritten | +0,10 mm, also angehoben |

Der Y-Versatz wurde ausdrücklich entlang der Maschinen-Y-Achse aufgebracht, nicht senkrecht zur schrägen Kante. Er entspricht deshalb nicht exakt derselben normalen Spanbreite. Der lineare Z-Verlauf blieb erhalten; ab Durchgang 3 wurde er insgesamt um 0,10 mm angehoben und bei allen weiteren Durchgängen so beibehalten.

Jeder Schnittdurchgang lief wie folgt:

- Auf Z 46,70 zum verlängerten Anfang der jeweils versetzten Linie, XY-Vorschub 300 mm/min.
- Am verlängerten Anfang mit 120 mm/min auf den zugehörigen Start-Z-Wert absenken.
- Die XYZ-Linie mit 150 mm/min einmal in Richtung A → B abfahren.
- Nach bestätigtem Bewegungsende auf Z 46,70 anheben, Z-Vorschub 180 mm/min.

Beim letzten Durchgang lagen die Schnittpunkte bei **S = X 185,2570 / Y 189,8069 / Z 27,5554** und **E = X 228,1720 / Y 200,8225 / Z 26,1784**. Danach stand das Werkzeug bei X 228,17 / Y 200,82 / Z 46,70.

**Ergebnis:** Alle vierzehn seitlich zugestellten Durchgänge wurden vom Controller bestätigt. Anschließend wurde auf Benutzerwunsch ein vollständiges `G28` einschließlich Z ausgeführt und mit `ok` abgeschlossen. Endanzeige: **X 0 / Y 230 / Z 85**. Die Spindel blieb manuell zu schalten.

## Energieeinstellungen und Schlussfolgerungen

Auf dem verwendeten Laptop wurde das separate Profil **„CNC - wach bleiben“** aktiviert. Im Netz- und Akkubetrieb wurden automatischer Standby, Ruhezustands-Timeout, Bildschirm-Timeout und selektives USB-Energiesparen deaktiviert. Der Sender für die fortgesetzte Taschenbearbeitung setzte zusätzlich eine Windows-Wachhalteanforderung für seine Laufzeit.

Das alte Profil „Ausbalanciert“ blieb erhalten und lässt sich auf diesem Laptop mit `powercfg /setactive SCHEME_BALANCED` wieder aktivieren. Beim CNC-Betrieb Netzteil anschließen und den Deckel offen lassen. Diese Maßnahmen adressieren Energiesparen, garantieren aber keine ausfallsichere USB-Verbindung.

Für weitere Sitzungen festhalten:

- Nach USB-Ausfall keinen Fräsauftrag automatisch fortsetzen. Versorgung, Controllerzustand, reale Position und Referenzierung klären.
- Freiraum vor jeder X/Y-Fahrt sicherstellen; ein angezeigter Z-Wert nach Reset ist dafür nicht ausreichend.
- Nach Fräserwechsel Oberfläche neu antasten und speichern; Maschinenhoming ersetzt das Antasten nicht.
- Nach Werkstückbewegung Ausrichtung erneut prüfen, bevor Offsets oder alte Bahnen verwendet werden.
- Nutzerangaben wie „Z +20“ oder „25 mm nach oben“ beziehen sich hier auf die aktuelle Position beziehungsweise die bestätigte Oberfläche, nicht auf einen absoluten Z-Wert.
- Radiuskorrektur und Bezug der DXF ausdrücklich festhalten: Fertigkontur und Fräsermittelbahn sind unterschiedliche Größen.

## Lokale Nachweise

Die Quelldatei, erzeugten G-Code-Dateien und Sitzungszustände lagen außerhalb dieses Repositorys unter `D:\gcode`. Sie werden durch dieses Protokoll nicht automatisch mitversioniert. Wesentliche lokale Dateien:

- `26-11-17_1203_conn_cut.setup.json`: ursprünglicher Bezug, Werkzeug und Konturgeometrie.
- `26-11-17_1203_conn_cut.interruption.json`: gesicherter Unterbrechungsstand des ersten Laufs.
- `26-11-17_1203_conn_cut.tool-change.json`: neue Z-Oberfläche, Werkzeugwechsel und bestätigte Ausrichtung.
- `26-11-17_1203_conn_cut.pocket3-d2-air.json`: kompensierte Kontur der bestätigten Probefahrt.
- `26-11-17_1203_conn_cut.pocket34-d2.run-status.json`: Abschluss von Taschen 3 und 4.
- `line-20261117-131102.setup.json`: Punkte A/B, Verlängerungen, Z-Verlauf und alle vierzehn Schnittdurchgänge.
- `cnc-power-profile.json`: ursprüngliches und aktiviertes Energieprofil des Laptops.

Die hier dokumentierten Ausführungsbestätigungen belegen den Controllerablauf. Eine unabhängige Vermessung der gefertigten Konturen oder Kante wurde in dieser Sitzung nicht dokumentiert.
