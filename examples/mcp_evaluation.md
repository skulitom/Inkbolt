# Fixed MCP agent evaluations

The following XML defines ten original, read-only questions used by the independent MCP evaluation test. The test creates its own isolated fixture and checks each answer.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<evaluation>
  <!-- Seeded by tests/test_mcp_evaluation.py in an explicit temporary session root.
       All questions use only read/inspect/history/diff/export against fixed revisions. -->
  <qa_pair><question>In session evaluation, compare committed revisions 0 and 1, find the moved leaf object, then inspect revision 1. What is its rightmost world geometry coordinate? Return a number.</question><answer>11</answer></qa_pair>
  <qa_pair><question>Read both committed revisions 0 and 1 of evaluation and compare their rendered output. How many scale-1 pixels changed when the warm object moved? Return the count.</question><answer>8</answer></qa_pair>
  <qa_pair><question>Page evaluation's history one entry at a time, then verify which action first returns to the original content without decreasing the revision. Return its action name.</question><answer>undo</answer></qa_pair>
  <qa_pair><question>Read evaluation revision 0, inspect its boards and independently export them. Which board has the greater pixel area? Return its item ID.</question><answer>wide</answer></qa_pair>
  <qa_pair><question>Inspect evaluation revision 0 and compare the actual occupied pixel areas of its two independent board exports. What is the name of the object with greater painted area?</question><answer>Warm</answer></qa_pair>
  <qa_pair><question>Find the named saved point in evaluation, compare its contents with committed revision 1, and identify when the name was recorded. Return the saved point's revision number.</question><answer>2</answer></qa_pair>
  <qa_pair><question>Use history and pixel comparison to decide whether evaluation revision 3 restores revision 0 exactly despite a different revision number. Return True or False.</question><answer>True</answer></qa_pair>
  <qa_pair><question>Read evaluation revision 0, find its larger artboard, then independently decode that board's PNG. How many pixels are fully transparent? Return the count.</question><answer>120</answer></qa_pair>
  <qa_pair><question>Inspect evaluation revision 0 and export each board in its own local coordinates. What is the sum of the two PNG pixel areas, excluding unused pasteboard space? Return the count.</question><answer>224</answer></qa_pair>
  <qa_pair><question>Page evaluation's committed history to find the geometry edit, recover its original receipt, and compare that result with the latest head. Which request ID retrieves the moved document even after undo? Return that request ID.</question><answer>shift</answer></qa_pair>
</evaluation>
```
