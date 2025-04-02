# FAQ: ESPP2 verktøy for beregning av skatt på utenlandske aksjer

## Ofte stilte spørsmål:
**Q: ESPP valutakurs**

**A:** Valutakursen som benyttes er Oracle P&L 6 månder gjennomsnittskurs. Denne kursen publiseres internt for hvert ESPP kjøptstidspunkt.

**Q: ESPP inngangsverdi i NOK**

**A:** ESPP inngangsverdien i NOK er aksjens FMV på kjøpstidspunktet multiplisert med ESPP valutakursen på samme dag.
Den rabatterte prisen som ansatt betaler for aksjene er ikke tatt med i beregningen, siden forskjellen mellom FMV og rabattert pris er rapportert som inntektsskatt.

**Q: Skjermingsfradrag**

**A:** Skjermingsfradrag er lagt til også for ESPP aksjer mottatt 31/12 i inntektsåret. Dette skjermingsfradraget taes med videre til neste år.
Skjermingsfradraget for aksjer som beholdes over nyttår får skjermingsfradrag og brukes når tilgjengelig for å redusere skatt på utbytte. Hvis aksjen har oppspart skjermingsfradrag fra før og den selges med gevinst, brukes skjermingsfradraget for å redusere skatt på gevinsten.

**Q: Valutakurs for utbytte**

**A:** Valutakursen som benyttes er Norges bank sin valutakurs på utbyttetidspunktet.

**Q: RSU inngangsverdi i NOK**

**A:** Inngangsverdien av RSUer er gitt av Norges bank sin valutakurs på tildelingstidspunktet multiplisert med RSUens rapporterte FMV.

**Q: Skattemessig behandling av aksjesalg i utenlandsk valuta (valutagevinst og sammenslåingsprinsippet)**

**A:** ❓ Hva er sammenslåingsprinsippet?

Sammenslåingsprinsippet innebærer at valutakursendringer knyttet til kjøp og salg av et formuesobjekt (som aksjer) inngår i gevinst- eller tapsberegningen for det underliggende objektet. Valutaen vurderes ikke som en egen skattemessig størrelse så lenge den er en integrert del av transaksjonen.

Dette gjelder særlig når:
- Aksjer er kjøpt og solgt i utenlandsk valuta (f.eks. USD),
- Og valutavekslingen skjer automatisk eller umiddelbart etter salget.

Referanse: Rt. 1929 s. 369

---

❓ Når skal valutagevinst/-tap vurderes separat?

Valutagevinst eller -tap skal vurderes separat når den utenlandske valutaen blir stående som en **egen formuespost**, og følgende kriterier er oppfylt:

- Beløpet i utenlandsk valuta ble **ikke vekslet umiddelbart**, og
- Skattyter hadde **kontroll over tidspunktet for veksling**, og
- Det foreligger **kursendringer mellom salgsdato og vekslingsdato**.

I slike tilfeller gjelder ikke sammenslåingsprinsippet, og valutagevinst/-tap må tidfestes på vekslingstidspunktet og rapporteres som kapitalinntekt (22 % skatt).

---

❓ Tidfestes aksjegevinsten på salgsdato eller vekslingsdato?

Aksjegevinst **tidfestes på salgsdato**, uavhengig av når valutavekslingen skjer. Dette følger realisasjonsprinsippet, jf. skatteloven § 5-1 (2) og § 9-2.

Valutagevinst/-tap (dersom det skilles ut) tidfestes **på vekslingstidspunktet**.

---

❓ Kan man bruke valutakurs på vekslingsdato hvis vekslingen skjer noen dager etter salget?

Dersom valutavekslingen skjer **automatisk eller innen svært kort tid**, og skattyter **ikke har styrt tidspunktet for veksling**, kan hele transaksjonen regnes som én samlet realisasjon. Da kan valutakursen ved veksling brukes i gevinstberegningen uten å skille ut valutagevinst/-tap.

---

✅ Oppsummering – når skal valutagevinst føres separat?

| Situasjon | Sammenslåingsprinsippet gjelder? | Valutagevinst/-tap vurderes separat? |
|----------|-------------------------------|-------------------------------|
| Aksjer selges og valuta veksles automatisk eller umiddelbart | ✅ Ja | ❌ Nei |
| Aksjer selges og valuta holdes i flere dager med kursendring | ❌ Nei | ✅ Ja |
| Skattyter har kontroll over vekslingsdato | ❌ Nei | ✅ Ja |

---

📌 Anbefalt praksis

- **Før kun aksjegevinst** dersom valutaelementet er en integrert del av salget.
- **Før valutagevinst/-tap separat** dersom valutaen beholdes som formuesobjekt og veksles senere.
- Dokumenter relevante datoer, valutakurser og vekslingskurs (f.eks. fra megler, bank eller Norges Bank).

---

## 📎 Kilder

- Rt. 1929 s. 369 (sammenslåingsprinsippet)
- Skatteloven §§ 5-1, 9-2, 14-2
- Skatteetaten.no – veiledning om valutagevinst og aksjetransaksjoner

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

## Gjenskape transaksjonshistorikk. Hvordan gjør jeg det?
**Q: Kan jeg laste opp flere transaksjonsfiler samtidig?**

**A:** Ja, du kan benytte deg av den eksperimentelle versjonen på rf1159-staging.rd.cisco.com for å laste opp flere transaksjonsfiler som er lastet ned fra Schwab. Merk at Schwab kun tillater eksport av transaksjonsdata i fireårsblokker. Det er viktig at du eksporterer hele din transaksjonshistorikk i ikke-overlappende blokker. Verktøyet vil gi deg nødvendige instruksjoner. Når du blir spurt om din beholdningsfil, velg "Nei".
You can try rf1159-staging.rd.cisco.com, an experimental version that supports uploading multiple transaction files downloaded from Schwab (Schwab only support exporting in 4 year chunks). Note you need to export ALL of your history, in non-overlapping chunks, the tool will give you instructions. Select "No" when asked about your holdings file.

## Feilmeldinger

#### ERROR:espp2.portfolio:Dividend error. Expected <x> shares, holding: <y>
Det er mottatt utbytte for <x> aksjer mens verktøyet beregner at beholdningen er <y> aksjer.
Dette kan typisk skyldes at det er noe galt med beholdningen fra forrige år. Sjekk at beholdningen er riktig.

#### ERROR:espp2.main:Expected source tax: <x> got: <y>
Verktøyet forventer at det trekkes 15% kildeskatt. Hvis det har vært trukket mer, er det en indikasjon på at W8-BEN ikke er oppdatert hos aksjemegleren.
