function run(argv) {
    const request = JSON.parse(argv[0]);
    const mail = Application('Mail');
    const op = request.operation, p = request.payload;
    if (op === 'mail.read') {
        const since = new Date(p.since + 'T00:00:00Z');
        const messages = mail.inbox.messages;
        const start = p.offset || 0;
        const count = Math.min(messages.length, start + p.limit);
        const result = [];
        // Bound the Apple event reads before fetching message content.
        // Evaluating whose(... )() first can materialise a large Inbox and time out.
        for (let i = start; i < count; i++) {
            const m = messages[i];
            const received = m.dateReceived();
            if (received < since) continue;
            const mid = m.messageId();
            if (!mid) continue;
            result.push({id: mid, title: m.subject(), body: m.content().slice(0,16000),
                received: received.toISOString(),
                url: 'message://%3C' + encodeURIComponent(mid.replace(/^<|>$/g,'')) + '%3E'});
        }
        return JSON.stringify(result);
    }
    if (op === 'mail.flag' || op === 'mail.mark_read') {
        const matches = mail.inbox.messages.whose({messageId: p.id})();
        if (matches.length !== 1) throw new Error('Message missing or ambiguous in Inbox.');
        const m = matches[0];
        if (op === 'mail.flag') m.flaggedStatus = p.value;
        else m.readStatus = p.value;
        return JSON.stringify({id: p.id, changed: true});
    }
    throw new Error('Unknown Mail operation.');
}
