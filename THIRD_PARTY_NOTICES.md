# Third-party notices

`tablecodec` is MIT-licensed (see [LICENSE](LICENSE)). It includes work
adapted from the following third-party projects, whose license terms are
reproduced below.

## docling-ibm-models

The OTSL grid-reconstruction logic in
`src/tablecodec/codecs/_otslgrid.py` (the anchor-centric scan, the
`check_right` / `check_down` span runs, and the 2D-span registry in
`build_anchors`) is adapted from the `otsl_to_html` algorithm in:

- Project: docling-project/docling-ibm-models
- File: `docling_ibm_models/tableformer/otsl.py`
- URL: <https://github.com/docling-project/docling-ibm-models>

It was reimplemented for tablecodec's neutral Internal Representation
(it emits `GridCell` spans rather than HTML strings) and carries no
third-party runtime imports. The original is offered under the MIT
License:

```
MIT License

Copyright (c) 2024 International Business Machines

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
```

## IBM PubTabNet — TEDS metric

The TEDS similarity implementation in `src/tablecodec/teds.py` (the apted
tree construction, the rename-cost rule, and the `1 - dist / max_nodes`
formula) is adapted from:

- Project: ibm-aur-nlp/PubTabNet
- File: `src/metric.py`
- URL: <https://github.com/ibm-aur-nlp/PubTabNet/blob/master/src/metric.py>

Changes: the entry point is IR-native (`teds(pred, true)` over
`TableSample`s), the normalized Levenshtein is reimplemented in pure Python
(replacing the `distance` package), and the batching/parallelism
(`tqdm`, `parallel_process`) is removed. The original code is offered under
the Apache License 2.0:

```
Copyright 2020 IBM
Author: peter.zhong@au1.ibm.com

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
