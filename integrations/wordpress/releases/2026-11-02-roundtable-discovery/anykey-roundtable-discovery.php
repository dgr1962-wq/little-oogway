<?php
/** Plugin Name: AnyKey Roundtable Discovery and Reading Layout
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }
add_action('wp_head', static function () { ?>
<style id="anykey-reading-center-20261102">
/* Keep the reading card centered when there is no room for balanced rails.
   The existing keyboard-accessible page-map drawer supplies navigation. */
@media (min-width:901px) and (max-width:1499px) {
 .shell.content-grid {width:min(864px,calc(100% - 30px));grid-template-columns:minmax(0,1fr)}
 .content-grid > .conversation-rail,.content-grid > .section-sidebar-stack {display:none}
 .conversation-dock {display:block}
}
.conversation-dock {bottom:88px}
.ak-roundtable-door {margin:1.25rem auto;padding:1.2rem;border:1px solid #cfc5ad;border-radius:12px;background:#f6f1e6;color:#24211d;overflow-wrap:anywhere}
.tbs-launch .ak-roundtable-door p,.tbs-launch .ak-roundtable-door h2 {color:#24211d}
.ak-roundtable-door h2 {margin:0 0 .65rem;font-size:1.5rem}
.ak-roundtable-door a {color:#185769;text-decoration:underline}
.ak-roundtable-door ul {padding-left:1.25rem}
</style>
<?php }, 99);
function ak_public_roundtable_session_006() {
 $p=get_page_by_path('session-006-buried-sky-audiobook-direction',OBJECT,'ak_rt_session');
 return $p && $p->post_status==='publish' ? $p : null;
}
add_filter('the_content',static function($content){
 if(!is_main_query()||!in_the_loop()||!is_singular())return $content;
 if(is_page('the-buried-sky') && strpos($content,'id="launch-film"')!==false){
  $note='<aside class="ak-roundtable-door" aria-label="A note from the author about the song"><h2>Before you press play</h2><p>Darren loves this film, but felt that “You’re Welcome” could sound condescending without its backstory. The Maui reference is part of the theatrical joke. In our own creative conversations, “you’re welcome” became a recurring playful punchline, which found its way into the song.</p><p>Read the swagger as a character performance and a shared laugh about making the book—not a claim that its creators are above the audience. <a href="'.esc_url(home_url('/project-laboratory/music-media-history/')).'">Explore the music and media production history →</a></p></aside>';
  $content=preg_replace('/(<section\b[^>]*\bid="launch-film"[^>]*>)/', '$1'.$note, $content,1);
 }
 $session=ak_public_roundtable_session_006();
 $hub=esc_url(home_url('/ai-round-table/'));
 $book=esc_url(home_url('/books/the-buried-sky/'));
 $history=esc_url(home_url('/project-laboratory/ai-roundtable-history/'));
 if(is_page('ai-round-table')){
  $links=$session?'<li><a href="'.esc_url(get_permalink($session)).'">Session 006: Directing The Buried Sky — audiobook production question and recorded discussion</a></li>':'';
  return '<section class="ak-roundtable-door" aria-labelledby="roundtable-public-title"><h2 id="roundtable-public-title">Roundtable — public sessions</h2><p>Start with the question, read the attributed contributions, and follow the outcome back to its project. These public records are reviewed derivatives, not the private live cockpit.</p><ul>'.$links.'<li><a href="'.$history.'">Roundtable project history and implementation record</a></li></ul><p><strong>Current update · November 2, 2026:</strong> Gemini has joined the configured table alongside Little Oogway, ChatGPT, Claude, and DeepSeek. Availability is recorded per session; a missing or timed-out participant contributes no vote. Earlier dated field notes below describe the system at that time.</p><p>Only cleared sessions appear here. Unpublished fiction and private memory remain outside this public collection.</p></section>'.$content;
 }
 if(!$session)return $content;
 if(is_page('the-buried-sky')||is_page('ai-roundtable-history')){
  return $content.'<aside class="ak-roundtable-door" aria-label="Related public roundtable"><h2>Follow the question to the table</h2><p>How should The Buried Sky become an audiobook while preserving provenance and human editorial authority?</p><p><a href="'.esc_url(get_permalink($session)).'">Read Session 006: the production proposal, reviews, and unresolved questions →</a></p><p><a href="'.$hub.'">Browse public Roundtable sessions</a></p></aside>';
 }
 if(get_the_ID()===$session->ID){
  return '<nav class="ak-roundtable-door" aria-label="Roundtable record navigation"><a href="'.$hub.'">← All public Roundtable sessions</a> · <a href="'.$book.'">The Buried Sky project</a> · <a href="'.$history.'">Roundtable implementation history</a></nav>'.$content;
 }
 return $content;
},30);
