import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="Uses the macOS JavaScript interpreter.")
@pytest.mark.parametrize("since,expected", [("2026-10-01", 2), ("2026-11-01", 0)])
def test_mail_read_limits_references_before_fetching_content(since, expected):
    # This fake Application never contacts Mail or requests macOS permission.
    fixture = """
    const messages = [0,1,2,3].map(function(i) {
        return {messageId: function(){return 'test-'+i;},
                subject: function(){return 'Synthetic';},
                content: function(){if(i>=2)throw Error('Read limit exceeded'); return 'Test text';},
                dateReceived: function(){return new Date('2026-10-24T01:00:00Z');},
                properties: function(){return {messageId:this.messageId(),subject:this.subject(),
                                              content:this.content(),dateReceived:this.dateReceived()};}};
    });
    const FakeApplication = function(name){return {inbox: {messages: messages}};};
    """
    script = (Path(__file__).parents[1] / "src/migine/native_mail.js").read_text()
    script = script.replace("Application('Mail')", "FakeApplication('Mail')")
    request = json.dumps({"operation": "mail.read", "payload": {"since": since, "limit": 2}})
    response = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", fixture + script, request],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert len(json.loads(response.stdout)) == expected
