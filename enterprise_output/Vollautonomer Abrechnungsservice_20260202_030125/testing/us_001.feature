@smoke @regression
Feature: Automatische Fakturierung nach POD-Validierung
  As a Accountant
  I want to automatisch eine Rechnung nach erfolgreicher POD-Validierung generieren lassen
  So that um zeitnahe, korrekte Abrechnung sicherzustellen und eine prüfbare Nachvollziehbarkeit zu gewährleisten

  Background:
    Given ein Auftrag existiert im Abrechnungssystem
    And die POD-Validierung ist technisch verfügbar

  @smoke @happy-path @regression
  Scenario: Erzeuge Rechnung nach erfolgreicher POD-Validierung
    # Happy path für automatische Rechnungserzeugung bei vollständigen Pflichtdaten
    Given der Auftrag ist erfolgreich POD-validiert
    And alle abrechnungsrelevanten Pflichtdaten sind vollständig
    When die POD-Validierung abgeschlossen wird
    Then wird automatisch eine Rechnung erzeugt
    And die Rechnung ist dem Auftrag zugeordnet

  @negative @regression
  Scenario Outline: Keine Rechnung bei fehlenden Pflichtdaten
    # Fehlende Pflichtdaten verhindern Rechnungserzeugung und protokollieren Fehler
    Given der Auftrag ist POD-validiert
    And Pflichtdaten fuer die Rechnungsstellung fehlen: <fehlendes_feld>
    When die automatische Rechnungsstellung angestossen wird
    Then wird keine Rechnung erzeugt
    And der Vorgang wird mit Fehlerstatus und Begruendung protokolliert

    Examples:
      | fehlendes_feld |
      | Rechnungsempfaenger |
      | Steuerkennzeichen |
      | Abrechnungsbetrag |

  @negative @regression
  Scenario: Keine doppelte Rechnung bei erneuter POD-Verarbeitung
    # Erneute POD-Validierung darf keine Doppelrechnung erzeugen
    Given eine Rechnung ist bereits fuer den Auftrag erzeugt
    When die POD-Validierung erneut verarbeitet wird
    Then wird keine doppelte Rechnung erstellt
    And der Versuch wird als Duplikat protokolliert

  @edge @regression
  Scenario Outline: Grenzfall mit minimalen Pflichtdaten
    # Boundary test fuer genau vollstaendige Mindestdaten
    Given der Auftrag ist erfolgreich POD-validiert
    And genau die minimal erforderlichen Pflichtdaten sind vorhanden: <datenstatus>
    When die POD-Validierung abgeschlossen wird
    Then wird eine Rechnung erzeugt
    And die Rechnung enthaelt nur die Pflichtangaben

    Examples:
      | datenstatus |
      | nur Pflichtfelder, keine optionalen Felder |

  @negative @regression
  Scenario Outline: Fehler bei ungueltigem POD-Validierungsstatus
    # Error scenario wenn POD-Validierung nicht erfolgreich ist
    Given der Auftrag hat den POD-Validierungsstatus <status>
    When die automatische Rechnungsstellung angestossen wird
    Then wird keine Rechnung erzeugt
    And der Vorgang wird mit Fehlerstatus und Begruendung protokolliert

    Examples:
      | status |
      | fehlgeschlagen |
      | ausstehend |
