# ESPP2 verktøy for beregning av skatt på utenlandske aksjer

## ESPP
### ESPP valutakurs
Valutakursen som benyttes er Oracle P&L 6 månder gjennomsnittskurs. Denne kursen publiseres internt for hvert ESPP kjøptstidspunkt.

### ESPP inngangsverdi i NOK
ESPP inngangsverdien i NOK er aksjens FMV på kjøpstidspunktet multiplisert med NB valutakursen.
Den rabatterte prisen som ansatt betaler for aksjene er ikke tatt med i beregningen, siden forskjellen
mellom FMV og rabattert pris er rapportert som inntektsskatt.

### Skjermingsfradrag
Skjermingsfradrag er lagt til også for ESPP aksjer mottatt 31/12 i inntektsåret. Dette skjermingsfradraget taes med videre til neste år.
Skjermingsfradraget for aksjer som beholdes over nyttår får skjermingsfradrag og brukes når tilgjengelig for å redusere skatt på utbytte. Hvis akjsen har oppspart skjermingsfradrag fra før og den selges med gevinst, brukes skjermingsfradraget for å redusere skatt på gevinsten.

## Utbytte
### Valutakurs for utbytte
Valutakursen som benyttes er Norges bank sin valutakurs på utbyttetidspunktet.

## RSU
### RSU inngangsverdi i NOK
Inngangsverdien av RSUer er gitt av Norges bank sin valutakurs på tildelingstidspunktet multiplisert med RSUens FMV.

## Litt forskjellig
### Gevinst/Tap på aksjer og gevinst/tap på valuta
Verktøyet følger sammenslåingsprinsippet. Slik at et eventuelt valutatap eller gevinst slåes sammen med den underliggene aksjetransaksjonen.
Selges derimot aksjer i år 1 og valuta overføres i år 2, betrakes dette som to uavhengige transaksjoner.
Aksjegevinst/tap regnes da mot Norges bank sin valutakurs på salgstidspunktet.
Valutagevinst/tap regnes mot Norges bank sin valutakurs på overføringstidspunktet.
Inngangsverdien til valutaen er gitt av NBs valutakurs på salgstidspunktet.

## Morgan Stanley import

Morgan's transaksjonsdata forvitrer over tid. Hvis man ikke har holdingsfilen for ifjor, og må regenerere denne fra transaksjonsdata så vil verktøyet resette skjermingsfradrag til 0 for alle posisjoner før siste utbyttedato. Dette fordi transaksjonsdata ikke inneholder de eksplisitte utbyttene og verktøyet ikke kan vite hvordan skjermingsfradrag har blitt brukt i tidligere år. Verktøyet prøver her å være så konservativt som mulig.

## Feilmeldinger

#### ERROR:espp2.portfolio:Dividend error. Expected <x> shares, holding: <y>
Det er mottatt utbytte for <x> aksjer mens verktøyet beregner at beholdningen er <y> aksjer.
Dette kan typisk skyldes at det er noe galt med beholdningen fra forrige år. Sjekk at beholdningen er riktig.

#### ERROR:espp2.main:Expected source tax: <x> got: <y>
Verktøyet forventer at det trekkes 15% kildeskatt. Hvis det har vært trukket mer, er det en indikasjon på at W8-BEN ikke er oppdatert hos akjsemegleren.