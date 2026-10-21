# Third-party notices and acknowledgements

## Immergas Dominus by JoTu

Thanks to [JoTu's Immergas Dominus integration](https://github.com/jotuera/immergas-dominus)
for public Dominus protocol references. The EXA client's identification alphabet
matches that project's `MAP1` / `MAP2`; its CRC and OpenTherm framing provide
related protocol references. We retain the upstream MIT notice below to preserve
attribution for this shared material.

Reference revision: [`139d3e660dbf503a306a9a154a17b332b874e472`](https://github.com/jotuera/immergas-dominus/tree/139d3e660dbf503a306a9a154a17b332b874e472),
particularly `custom_components/immergas_dominus/dominus_client.py` and
`opentherm_client.py`. This EXA integration has a separate async transport,
control-ownership safeguards and Home Assistant implementation. Compatibility
and hardware-validation claims from the upstream project do not transfer here.

### Upstream license

MIT License

Copyright (c) 2026 JoTu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Protocol research and manufacturer materials

The implementation also uses interoperability findings from local examination
of the official application and public protocol/configuration references,
including [harykx/dominus](https://github.com/harykx/dominus). A public reference
is not a license grant: no license is claimed for that repository's configuration
or label files. Those files, the application/APK, decompiled application sources
and manufacturer artwork are not bundled with this integration.

The project's MIT license covers its code, not third-party applications,
manufacturer materials or trademarks. Immergas and Dominus names are used only
to identify the intended compatible equipment. This is an unofficial community
project, not affiliated with or endorsed by Immergas. No clean-room development
or manufacturer authorization is claimed.
