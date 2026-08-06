/* Session switcher toggle — from BudgetFlow, hardcoded for billetterie */
(function(){
  function placeFloat(wrap){
    var menu = wrap._swMenu, trig = wrap.querySelector('[data-sw-trigger]');
    if(!menu || !trig) return;
    var r = trig.getBoundingClientRect();
    menu.style.setProperty('--sw-top', (r.bottom + 8) + 'px');
    if(menu.classList.contains('right')){
      menu.style.setProperty('--sw-right', (window.innerWidth - r.right) + 'px');
    } else {
      menu.style.setProperty('--sw-left', r.left + 'px');
    }
  }
  function openWrap(wrap){
    var menu = wrap.querySelector('.sw-menu');
    if(!menu) return;
    wrap._swMenu = menu;
    wrap._swHome = menu.parentNode;
    wrap._swNext = menu.nextSibling;
    document.body.appendChild(menu);
    menu.classList.add('sw-float');
    wrap.classList.add('open');
    placeFloat(wrap);
  }
  function closeWrap(wrap){
    var menu = wrap._swMenu;
    if(menu){
      menu.classList.remove('sw-float');
      menu.style.cssText = '';
      if(wrap._swHome) wrap._swHome.insertBefore(menu, wrap._swNext || null);
    }
    wrap.classList.remove('open');
    wrap._swMenu = wrap._swHome = wrap._swNext = null;
  }
  function closeAll(){ document.querySelectorAll('.sw-wrap.open').forEach(closeWrap); }

  document.addEventListener('click', function(e){
    var trig = e.target.closest('[data-sw-trigger]');
    if(trig){
      var wrap = trig.closest('.sw-wrap');
      var wasOpen = wrap.classList.contains('open');
      closeAll();
      if(!wasOpen) openWrap(wrap);
      e.stopPropagation();
      return;
    }
    if(!e.target.closest('.sw-menu')) closeAll();
  });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeAll(); });
  window.addEventListener('resize', function(){ document.querySelectorAll('.sw-wrap.open').forEach(placeFloat); });
  window.addEventListener('scroll', function(){ document.querySelectorAll('.sw-wrap.open').forEach(placeFloat); }, true);
})();
