# Red Sea air-roster research

Research cutoff: **2026-08-11**. This is a deliberately small gameplay roster,
not an exhaustive order of battle. Actor names identify the publicly documented
platform family; the balance values and visual markings are game abstractions.

## Saudi Arabia

- **F-15SA / F-15 fleet:** The U.S. Defense Security Cooperation Agency's
  3 February 2026 sustainment notice explicitly describes support for the Royal
  Saudi Air Force F-15 fleet. A U.S. Army account of Red Sands 2025 specifically
  identifies RSAF F-15SAs flying in the exercise. Sources:
  [DSCA F-15 Sustainment](https://www.dsca.mil/Press-Media/Major-Arms-Sales/Article-Display/Article/4396586/kingdom-of-saudi-arabia-f-15-sustainment),
  [U.S. Army Red Sands 2025](https://www.lineofdeparture.army.mil/Journals/Air-Defense-Artillery/ADA-Archive/2025-E-Edition/Red-Sands/).
- **AH-64 Apache:** The same U.S. Army exercise account records Saudi AH-64E
  participation. A 14 April 2026 U.S. Army Security Assistance Command article
  states that Royal Saudi Land Forces Aviation Command operates AH-64 Apaches;
  December 2025 DSCA notices also cover AH-64A/D/E sustainment and AH-64E
  training. Sources: [USASAC portfolio account](https://www.army.mil/article/291720/usasac_saudi_arabia_eye_fms_portfolio),
  [DSCA training notice](https://www.dsca.mil/Press-Media/Major-Arms-Sales/Article-Display/Article/4345481/kingdom-of-saudi-arabia-blanket-order-training),
  [DSCA logistics notice](https://www.dsca.mil/Press-Media/Major-Arms-Sales/Article-Display/Article/4345453/kingdom-of-saudi-arabia-cooperative-logistics-supply-support-arrangement-progra).

The implementation therefore uses an **F-15SA air-superiority fighter** and an
**AH-64E close-support helicopter**. The fighter's long-range air-to-air load is
the premium counter to aircraft; its small cannon reserve is deliberately weak
against heavy ground targets. The slower helicopter combines an anti-personnel
cannon with limited anti-vehicle rockets and remains vulnerable to fighters and
dedicated air defense.

## Yemen / Houthi forces

The in-game Yemen faction is a broad fictionalized faction. The documented
Samad-family evidence below concerns Houthi forces and must not be read as the
inventory of the internationally recognized Yemeni government.

- The UN Panel of Experts' **S/2019/83** report describes the UAV-X, likely known
  as Samad-2 or Samad-3, as usable for reconnaissance or attack with an estimated
  18 kg payload. [UN S/2019/83](https://documents.un.org/doc/undoc/gen/n19/006/48/pdf/n1900648.pdf)
- **S/2024/731** identifies a 19 July 2024 one-way UAV as similar to the Houthi
  Samad-3. **S/2025/650** reports continued Houthi one-way attack-UAV operations
  and retained UAV manufacturing capability. Sources:
  [UN S/2024/731](https://documents.un.org/api/symbol/access?l=en&s=S%2F2024%2F731&t=pdf),
  [UN S/2025/650](https://documents.un.org/api/symbol/access?l=en&s=S%2F2025%2F650&t=pdf).

The retained **Samad** is consequently a low-cost loitering one-way strike
actor: it scouts while approaching, commits to an irreversible terminal dive,
fires only at contact range, and is destroyed with its payload. It has no
return-to-base or rearm behavior.

## Scope and uncertainty

Public inventories, serviceability, sub-variants, and transfers can change or
remain undisclosed. These authoritative public sources establish platform
operation through the cutoff; they do not justify exact quantities. No quantity
claim is encoded in the game, and all costs, ammunition counts, reload timings,
damage, and AI weights are balance choices rather than real-world performance
claims.
