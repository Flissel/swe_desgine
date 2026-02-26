# User Flows

## FLOW-001: Automatische Rechnungsstellung nach POD-Validierung

**Actor:** Laura Becker
**Trigger:** Systemereignis: POD-Validierung abgeschlossen

Flow zur automatischen Erstellung einer Rechnung nach erfolgreicher POD-Validierung

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
| 1 | System empfängt Abschluss der POD-Validierung für einen Auftrag | Backend Prozess | POD-Validierungsergebnis wird verarbeitet |
| 2 | System prüft, ob alle abrechnungsrelevanten Pflichtdaten vorhanden sind (Decision) | Backend Prozess | Status der Vollständigkeit wird ermittelt |
| 3 | System prüft, ob bereits eine Rechnung für den Auftrag existiert (Decision) | Backend Prozess | Duplikatsstatus wird ermittelt |
| 4 | System erzeugt automatisch eine Rechnung | Backend Prozess | Rechnung wird erstellt und dem Auftrag zugeordnet |
| 5 | System protokolliert die erfolgreiche Erstellung und stellt Rechnung im Auftragskontext bereit | Auftragsdetail | Rechnung ist nachvollziehbar dokumentiert und abrufbar |

### Success Criteria

Rechnung wurde automatisch erstellt, dem Auftrag zugeordnet und protokolliert

### Error Scenarios

- Pflichtdaten fehlen: Keine Rechnung erstellt, Fehlerstatus und Begründung protokolliert
- Duplikat erkannt: Keine Rechnung erstellt, Duplikatversuch protokolliert
- Systemfehler bei Rechnungserstellung: Vorgang fehlgeschlagen und protokolliert

**Diagram:** See `user_flows/flow-001.mmd`

---

## FLOW-002: Monitoring-Dashboard anzeigen und überwachen

**Actor:** Laura Becker
**Trigger:** User öffnet das Monitoring-Dashboard

Flow zum Anzeigen von Workflow-Status, KPIs und Agent-Performance in Echtzeit inkl. Exception-Handling

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
| 1 | User meldet sich an und navigiert zum Monitoring-Dashboard (Decision) | Login / Navigation | Dashboard lädt und Zugriff ist autorisiert |
| 2 | System lädt Echtzeitdaten (Workflows, KPIs, Agent-Performance) (Decision) | Monitoring-Dashboard | Daten werden innerhalb von 5 Sekunden angezeigt |
| 3 | User überprüft Workflow-Status und KPIs | Monitoring-Dashboard | Aktuelle Status- und KPI-Kacheln sind sichtbar und aktuell |
| 4 | Dashboard aktualisiert automatisch oder User klickt auf 'Refresh' (Decision) | Monitoring-Dashboard | Neue Daten werden geladen und angezeigt |
| 5 | System erkennt Exception oder SLA-Verstoß (Decision) | Monitoring-Dashboard | Exception wird hervorgehoben mit Zeitstempel und Link zu Workflow-Details |
| 6 | User klickt auf den Exception-Link | Workflow-Details | Detailansicht des betroffenen Workflows wird geöffnet |

### Success Criteria

Dashboard zeigt innerhalb von 5 Sekunden aktuelle Workflow-Status, KPIs und Agent-Performance an; Exceptions werden hervorgehoben und verlinkt

### Error Scenarios

- Datenquelle nicht verfügbar: Fehlermeldung und letzter Daten-Zeitstempel
- Keine Berechtigung für Dashboardzugriff
- Aktualisierung fehlgeschlagen: Anzeige letzter erfolgreicher Stand

**Diagram:** See `user_flows/flow-002.mmd`

---

## FLOW-003: Bankkonto anlegen

**Actor:** Laura Becker
**Trigger:** User navigiert zu 'Bank Account Setup' und klickt auf 'Neues Bankkonto'

Flow zum Erfassen und Speichern von Bankkontodaten mit Validierung und Sicherheitskontrollen

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
| 1 | User oeffnet das Finanz-Dashboard | Finanz-Dashboard | Dashboard wird angezeigt |
| 2 | User klickt auf 'Bankkonten' im Navigationsmenu | Finanz-Dashboard | Bank Account Setup Seite wird geladen |
| 3 | User klickt auf 'Neues Bankkonto hinzufuegen' | Bank Account Setup | Leeres Bankkonto-Formular wird angezeigt |
| 4 | User gibt bank_name, account_holder, iban, bic, account_type und currency ein | Bank Account Setup | Eingaben werden im Formular erfasst |
| 5 | User klickt auf 'Speichern' (Decision) | Bank Account Setup | System startet Validierung und Duplikatpruefung |
| 6 | System validiert IBAN-Format und BIC-Existenz (Decision) | Bank Account Setup | Validierungsergebnis liegt vor |
| 7 | System prueft, ob IBAN bereits existiert (Decision) | Bank Account Setup | Duplikatpruefung abgeschlossen |
| 8 | System speichert Bankkonto mit Ende-zu-Ende-Verschluesselung und Tokenization | Bank Account Setup | Bankkonto wird gespeichert und in der Liste angezeigt |
| 9 | User sieht Erfolgsbestaetigung | Bank Account Setup | Success-Toast und Eintrag in der Bankkonto-Liste |

### Success Criteria

Bankkonto wird erfolgreich gespeichert, erscheint in der Liste und ist auditierbar

### Error Scenarios

- Ungueltiger IBAN-Format fuehrt zu Validierungsfehler
- BIC existiert nicht und verhindert das Speichern
- Duplikat-IBAN wird erkannt und blockiert
- Serverfehler verhindert das Speichern

**Diagram:** See `user_flows/flow-003.mmd`

---

## FLOW-004: Company Settings konfigurieren

**Actor:** Laura Becker
**Trigger:** User navigiert zu 'Company Settings'

Flow zum Aktualisieren der Unternehmensstammdaten inkl. Legal, Tax, Address und Billing Defaults

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
| 1 | User oeffnet das Hauptmenue und waehlt 'Company Settings' | Navigation / Dashboard | Company Settings Seite wird geladen |
| 2 | User waehlt aktive Entity aus dem Entity-Switcher (Decision) | Company Settings | Daten der gewaehlten Entity werden angezeigt |
| 3 | User aktualisiert Felder: company_name, tax_id, vat_number, address, contact_details, default_payment_terms | Company Settings | Eingaben werden im Formular angezeigt |
| 4 | User klickt 'Speichern' (Decision) | Company Settings | Validierung wird gestartet |
| 5 | System prueft tax_id und vat_number via automatischer Steuer-Validierung (Decision) | Company Settings | Gueltige Werte werden bestaetigt |
| 6 | System speichert die Einstellungen der aktiven Entity | Company Settings | Erfolgsnachricht wird angezeigt und Werte sind gespeichert |
| 7 | User wechselt zu einer anderen Entity und prueft deren Daten | Company Settings | Nur die Daten der neuen Entity werden angezeigt; vorherige Entity bleibt unveraendert |

### Success Criteria

Company Settings der aktiven Entity wurden erfolgreich validiert, gespeichert und korrekt angezeigt

### Error Scenarios

- Ungueltige tax_id oder vat_number blockiert Speichern und zeigt Fehlermeldung
- Serverfehler beim Laden oder Speichern der Einstellungen
- Fehlende Pflichtfelder verhindern das Speichern

**Diagram:** See `user_flows/flow-004.mmd`

---

## FLOW-005: Customer Management

**Actor:** Laura Becker
**Trigger:** User oeffnet den Bereich 'Customers'

Flow zum Verwalten von Kundenstammdaten inkl. Anlegen, Validierung und Bulk-Import mit Dublettenprüfung

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
| 1 | User oeffnet das Dashboard | Dashboard | Dashboard wird angezeigt |
| 2 | User klickt auf 'Customers' | Navigation | Customer List wird angezeigt |
| 3 | User klickt auf 'Neuen Kunden anlegen' | Customer List | Kundenformular oeffnet sich |
| 4 | User fuellt Kundenstammdaten aus (Name, Billing/Shipping Address, Tax ID, Payment Terms, Credit Limit, Preferred Payment Method) | Customer Form | Alle Pflichtfelder sind ausgefuellt |
| 5 | User klickt auf 'Speichern' (Decision) | Customer Form | System validiert Eingaben |
| 6 | System zeigt Validierungsfehler an | Customer Form | Fehlerhinweis mit fehlendem/ungueltigem Feld wird angezeigt |
| 7 | User korrigiert Eingaben und speichert erneut | Customer Form | Kunde wird gespeichert |
| 8 | System zeigt Customer List mit neuem Eintrag | Customer List | Neuer Kunde erscheint mit allen Details |
| 9 | User waehlt 'Bulk Import' | Customer List | Import-Dialog wird angezeigt |
| 10 | User laedt Importdatei hoch und startet Import (Decision) | Bulk Import Dialog | System verarbeitet Datei |
| 11 | System findet Dubletten (Tax ID oder Customer Name) (Decision) | Bulk Import Results | Dubletten werden markiert und Optionen angezeigt: Merge, Update, Skip |
| 12 | User waehlt Option fuer jede Dublette (Merge/Update/Skip) und bestaetigt | Bulk Import Results | System fuehrt ausgewaehlte Aktion aus und importiert restliche Datensaetze |
| 13 | System zeigt Import-Zusammenfassung | Bulk Import Summary | Import erfolgreich abgeschlossen, Customer List aktualisiert |

### Success Criteria

Kundenstammdaten werden korrekt angelegt oder importiert; Dubletten werden erkannt und behandelt; Validierungsfehler verhindern fehlerhafte Speicherung

### Error Scenarios

- Pflichtfelder fehlen oder Tax ID hat ungueltiges Format
- Serververbindung fehlgeschlagen
- Importdatei hat falsches Format oder ist beschaedigt
- Konflikt bei Dubletten-Merge kann nicht automatisch geloest werden

**Diagram:** See `user_flows/flow-005.mmd`

---

