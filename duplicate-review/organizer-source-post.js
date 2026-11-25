(async function startSourcePost() {
 const address = new URL(location.href);
 const params = address.searchParams;
 try {
  await refresh(true);
  const located = await api('source-post', {
   job: data.job,
   collection: params.get('sourceCollection'),
   post: params.get('sourcePost'),
   photo: params.get('sourcePhoto') || ''
  });
  if (located.job !== data.job) {
   navigation = [];
   sessionStorage.removeItem('organizer-back');
   await refresh(true);
  }
  if (located.job !== data.job) throw Error('The collection changed in another window. Reopen the post.');
  restoreSession();
  tab = 'posts';
  $('order').value = 'original';
  await open('post', located.post, 0, false, located.focus);
  for (const key of ['sourceCollection', 'sourcePost', 'sourcePhoto']) params.delete(key);
  history.replaceState(null, '', address);
  sessionReady = true;
  await saveSession().catch(e => toast(e.message));
  await related().catch(e => toast(e.message));
 } catch (e) {
  $('title').textContent = 'Original post unavailable';
  const message = el('div');
  const actions = el('div', undefined, 'row');
  actions.append(button('Try again', () => location.reload()));
  if (params.get('sourcePhoto')) {
   actions.append(button('Open whole post', () => {
    params.delete('sourcePhoto');
    location.assign(address);
   }));
  }
  actions.append(button('Continue in organizer', () => location.replace('/organizer')));
  message.append(el('p', e.message), actions);
  $('grid').replaceChildren(message);
 }
})();
