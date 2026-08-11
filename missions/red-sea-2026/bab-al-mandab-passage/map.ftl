briefing =
    FACTUAL CUTOFF: 11 AUGUST 2026

    Bab al-Mandab lies between the Arabian Peninsula and the Horn of Africa and connects the Red Sea with the Gulf of Aden and Arabian Sea. Public maritime authorities describe the Red Sea as a critical international trade corridor and emphasize that seafarers are civilians.

    Establish the Saudi coastal post, construct a Radar Dome and Tech Center, produce an additional Red Sea roster vehicle, reconnoiter three shoreline sectors, neutralize the mobile launchers, escort civilian ships around Mayyun, and hold Passage Control through the final escalation.

    Sourced background ends there. Every force, threat, route, incident, position, timing, and outcome in this mission is fictionalized gameplay.

establish-coastal-post = Build a Radar Dome and Tech Center; produce 1 M1A2S or SADS.
reconnoiter-coast = Scout all 3 coastal sectors before time expires.
neutralize-mobile-threats = Destroy all mobile launchers before civilian transit.
escort-civilian-shipping = Escort the required civilian ships around Mayyun.
hold-safe-passage = Keep Passage Control operational through the final attack.
preserve-navigation-beacons = Optional: Keep both navigation beacons operational.

actor-civilian-merchant =
    .name = Civilian Merchant Vessel
actor-passage-control =
    .name = Passage Control
actor-navigation-beacon =
    .name = Civilian Navigation Beacon
actor-mandab-rifle =
    .name = Saudi Coastal Scout
actor-mandab-at-team =
    .name = Saudi Anti-Armor Team
actor-mandab-engineer =
    .name = Saudi Combat Engineer

mandab-control = Mandab / الممر
saudi-maritime-command = Saudi / البحرية
civilian-shipping = Shipping / الملاحة

radio-mandab-opening-ar = هنا قيادة الممر. ابنوا مركز التقنية واستعدوا للعبور.
    Mandab Control. Build the Tech Center and prepare for transit.
radio-mandab-readiness-en = Tech online. Sweep the three coastal sectors.
    مركز التقنية جاهز. امسحوا القطاعات الساحلية الثلاثة.
radio-mandab-recon-ar = اكتمل المسح. منصات متحركة تهدد الممر؛ حيّدوها.
    Coast mapped. Mobile launchers found; destroy them.
radio-mandab-shipping-en = Civilian transit has begun. Hold both Mayyun lanes.
    بدأ العبور المدني. أمّنوا المسارين حول ميون.
radio-mandab-recovery-ar = سفينة متأخرة. قاطرة المرافقة تعيدها إلى المسار.
    Ship separated. The escort tug is returning it to lane.
radio-mandab-loss-en = Civilian ship lost. Protect the remaining convoy.
    فُقدت سفينة مدنية. احموا القافلة المتبقية.
radio-mandab-final-ar = بدأ الهجوم الأخير. أبقوا الممر مفتوحاً حتى اكتمال العبور.
    Final attack. Hold the passage until transit completes.
radio-mandab-beacon-lost-en = Navigation beacon lost. Optional objective failed.
    فُقدت منارة ملاحة. فشل الهدف الاختياري.
radio-mandab-victory-ar = اكتمل العبور. الممر آمن.
    Transit complete. The passage is secure.
radio-mandab-failure-en = Passage Control lost. Civilian transit suspended.
    فُقدت قيادة الممر. عُلّق العبور المدني.

mission-text-readiness = Build Tech Center + 1 roster vehicle ({ $seconds }s)
mission-text-recon = Coastal sectors scanned: { $scanned } / 3 ({ $seconds }s)
mission-text-threats = Mobile launchers remaining: { $remaining } ({ $seconds }s)
mission-text-shipping = Civilian ships secured: { $secured } / { $required }
mission-text-hold = Safe-passage hold: { $seconds }s remaining
mission-text-recovery = Escort tug recovery { $recoveries }: returning separated vessel to lane
