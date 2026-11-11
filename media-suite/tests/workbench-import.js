(async function (id) {
    const token = document.querySelector('script[nonce]').nonce;
    async function call(action, body) {
        const res = await fetch('/api/organizer/' + action, {
            method: body ? 'POST' : 'GET',
            headers: {'Content-Type':'application/json', 'X-Review-Token':token},
            body: body ? JSON.stringify(body) : undefined
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || action);
        return data;
    }
    const state = await call('state');
    const job = state.job;
    const catalog = await call('import-catalog', {job});
    await call('queue_individuals', {job, revision:state.state.revision, ids:[id],
        options:{destination:'main',favorite:true}, character_id:catalog.character_id, library_instance:catalog.library_instance});
    const plan = await call('transfer-preview', {job, include_sets:false});
    if (!plan.imports.length) throw new Error('The fixture import was missing');
    window.suiteImportStarted = true;
    for (const item of plan.imports) await call('transfer-import', {job,token:plan.token,id:item.id});
    const result = await call('transfer-apply', {job,token:plan.token});
    if (!result.checkpoint) throw new Error('Missing import checkpoint');
    return true;
})
