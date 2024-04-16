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

**A:** Sammenslåingsprinsippet gjelder. Slik at et eventuelt valutatap eller gevinst slåes sammen med den underliggene aksjetransaksjonen. Valutagevinst eller tap må da manuelt legges sammen med akjsegevinst/tap.

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

**Q: Hva om jeg selger ESPP aksjer fra før 2013?**

**A:** Vi har kun ESPP valutakurser fra 2013. Hvis du selger ESPP aksjer som er kjøpt før det må du manuelt finne og registrere disse i espp2/data.json filen.

**Q: ESPP aksjer kjøpt 31/12 men som ikke registreres hos broker før noen dager inn i neste år. Hvilker skatteår blir de registrert på?**

**A:** ESPP aksjer som er kjøpt 31/12 blir registrert på det året, selvom de ikke er synlige hos brokeren før noen dager senere. Det betyr at det beregnes formueskatt for disse aksjene for det året, men samtidig får man også skjermingsfradrag for dem.
Husk at det er viktig at transaksjonsfilen inneholder transaksjoner for januar for påfølgende år for å få med dette ESPP kjøpet. Hvis transaksjonsfilen kun inneholder 1/1-31/12 har verktøyet ingen mulighet til å detektere dette. Men du vil få en feilmelding til neste år.

**Q: Hva gjør jeg med aksjer kjøpt før 2006?**

**A:** Hvem vet. Skjermingsfradrag ble introdusert i 2006. Aksjer kjøpt tidligere støttes ikke av dette verktøyet.

**Q: Hvor henter dere data fra?**

**A:** Vi henter valutakurser via Norges Bank APIer. Finansdata (akjsekurser, utbytte og utbyttedatoer, ISIN numre etc) fra EOD (https://eodhd.com).
ESPP kurser og skjermingsrente er lagt inn manuelt.

**Q:Hvordan får jeg tilgang til web grensesnittet?**

**A:** Web-grensesnittet er foreløpig kun tilgjengelig internt.
Sjekk [ESPP tax discussion](webexteams://im?space=c53d9d80-104b-11e6-bbcf-e5d12042fad8).

**Q: Hva om tallene verktøyet rapporterer er feil?**

**A:** Si ifra til oss. Det kan være mange grunner til at utregningen blir feil. Feil i input, eller feil i utregningene i verktøyet. Husk at du alltid er ansvarlig selv for tallene du rapporterer til skatteetaten. Studer excel-arket nøye og sørg for at balansene ved inngangen og utgangen av skatteåret er korrekte.

**Q: Verktøyet gir en error eller warning. Kan jeg bare ignorere disse?**

**A:** Bare hvis du ikke bryr deg om å rapportere riktig. Se feilmeldinger under med typiske årsaker.

## Feilmeldinger

#### ERROR:espp2.portfolio:Dividend error. Expected <x> shares, holding: <y>
Det er mottatt utbytte for <x> aksjer mens verktøyet beregner at beholdningen er <y> aksjer.
Dette kan typisk skyldes at det er noe galt med beholdningen fra forrige år. Sjekk at beholdningen er riktig.

#### ERROR:espp2.main:Expected source tax: <x> got: <y>
Verktøyet forventer at det trekkes 15% kildeskatt. Hvis det har vært trukket mer, er det en indikasjon på at W8-BEN ikke er oppdatert hos akjsemegleren.
