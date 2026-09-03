from pathlib import Path

p = Path('pc-xr/main-v11.cpp')
t = p.read_text(encoding='utf-8')

basic_filtered = '        inputWriter_.Publish(true, filteredU, filteredV, triggerDown_);'
basic_plain = '        inputWriter_.Publish(true, u, v, triggerDown_);'
extended_plain = '        inputWriter_.Publish(true, u, v, triggerDown_, aDown_, gripDown_, stickX, stickY);'
extended_filtered = '        inputWriter_.Publish(true, filteredU, filteredV, triggerDown_, aDown_, gripDown_, stickX, stickY);'

if basic_filtered in t:
    # Pre-pass: let the v0.13.3 patch find its historical marker.
    t = t.replace(basic_filtered, basic_plain, 1)
    print('v0.13.3 adapter pre-pass applied')
elif extended_plain in t:
    # Post-pass: restore v0.13's single filtered UV path for cursor + CEF.
    t = t.replace(extended_plain, extended_filtered, 1)
    print('v0.13.3 adapter post-pass applied')
elif extended_filtered in t:
    print('v0.13.3 adapter already finalized')
else:
    raise SystemExit('No compatible XR pointer publish marker found')

p.write_text(t, encoding='utf-8')
