# FAQ: ESPP2 verktøy for beregning av skatt på utenlandske aksjer

## Ofte stilte spørsmål:
**Q: ESPP valutakurs**

**A:** Valutakursen som benyttes er Oracle P&L 6 månder gjennomsnittskurs. Denne kursen publiseres internt for hvert ESPP kjøptstidspunkt.

**Q: ESPP inngangsverdi i NOK**

**A:** ESPP inngangsverdien i NOK er aksjens FMV på kjøpstidspunktet multiplisert med Norges Bank valutakursen på samme dag.
Den rabatterte prisen som ansatt betaler for aksjene er ikke tatt med i beregningen, siden forskjellen mellom FMV og rabattert pris er rapportert som inntektsskatt.

**Q: Skjermingsfradrag**

**A:** Skjermingsfradrag er lagt til også for ESPP aksjer mottatt 31/12 i inntektsåret. Dette skjermingsfradraget taes med videre til neste år.
Skjermingsfradraget for aksjer som beholdes over nyttår får skjermingsfradrag og brukes når tilgjengelig for å redusere skatt på utbytte. Hvis aksjen har oppspart skjermingsfradrag fra før og den selges med gevinst, brukes skjermingsfradraget for å redusere skatt på gevinsten.

**Q: Valutakurs for utbytte**

**A:** Valutakursen som benyttes er Norges bank sin valutakurs på utbyttetidspunktet.

**Q: RSU inngangsverdi i NOK**

**A:** Inngangsverdien av RSUer er gitt av Norges bank sin valutakurs på tildelingstidspunktet multiplisert med RSUens rapporterte FMV.

**Q: Gevinst/Tap på aksjer og gevinst/tap på valuta**

**A:** Verktøyet følger sammenslåingsprinsippet. Slik at et eventuelt valutatap eller gevinst slåes sammen med den underliggene aksjetransaksjonen.
Selges derimot aksjer i år 1 og valuta overføres i år 2, betrakes dette som to uavhengige transaksjoner.
Aksjegevinst/tap regnes da mot Norges bank sin valutakurs på salgstidspunktet.
Valutagevinst/tap regnes mot Norges bank sin valutakurs på overføringstidspunktet.
Inngangsverdien til valutaen er gitt av NBs valutakurs på salgstidspunktet.

**Q: Kan jeg importere Morgan Stanley transaksjoner uten en holdingsfil fra ifjor?**

**A:** Morgan's transaksjonsdata forvitrer over tid. Hvis man ikke har holdingsfilen for ifjor, og må regenerere denne fra transaksjonsdata så vil verktøyet resette skjermingsfradrag til 0 for alle posisjoner før siste utbyttedato. Dette fordi transaksjonsdata ikke inneholder de eksplisitte utbyttene og verktøyet ikke kan vite hvordan skjermingsfradrag har blitt brukt i tidligere år. Verktøyet prøver her å være så konservativt som mulig.

**Q: Hvilke transaksjonsfilformater støtter ESPPv2 verktøyet?**

**A:** Hvis verktøyet ble brukt i fjor skal en av de to formatene under være tilstrekkelig.
- Schwab JSON (ny fra 2023)
- Morgan Stanley HTML

I tillegg støttes endel formater for å kunne generere fjorårets holdingfil hvis denne mangler.
- Schwab CSV
- Schwab CSV2 (ny fra 2032)
- ESPPv1 pickle file
- My_ESPP_Purchases XLS
- My_Stock_Transactions XLS
- TD Ameritrade CSV (vil fjernes siden TD er kjøpt av Schwab)

**Q: Er Web-grensesnittet tilgjengelig hvis jeg ikke lenger jobber for Cisco?**

**A:** Nei. Se under.

**Q: Hvordan kan jeg kjøre CLI verktøyet selv?**

**A:** ESPPv2 henter data fra åpne og proprietære kilder. Valutakurser hentes fra Norges Banks åpne APIer. Aksjedata, som historiske kurser, utbytte datoer, ISIN etc, hentes fra finanstjenesten EOD. Verktøyet har tidligere brukt tjenester fra Alpha Vantage og andre. Disse tjenestene er relativt kortlivede og ser ut til å endre betalingsmodell år for år.

For å bruke EOD kreves ett abonnement og en API key. Alternativt kan vi gi tilgang til cachede filer. Kontakt ESPPv2 support for videre veiledning.

## Feilmeldinger

#### ERROR:espp2.portfolio:Dividend error. Expected <x> shares, holding: <y>
Det er mottatt utbytte for <x> aksjer mens verktøyet beregner at beholdningen er <y> aksjer.
Dette kan typisk skyldes at det er noe galt med beholdningen fra forrige år. Sjekk at beholdningen er riktig.

#### ERROR:espp2.main:Expected source tax: <x> got: <y>
Verktøyet forventer at det trekkes 15% kildeskatt. Hvis det har vært trukket mer, er det en indikasjon på at W8-BEN ikke er oppdatert hos akjsemegleren.
