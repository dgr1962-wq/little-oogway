<?php
// One-shot, private CLI deployment. Never install this script in the web root.
if(PHP_SAPI!=='cli')exit(1);
$root=__DIR__;$web='/home/sparkles/domains/anykeycafe.com/public_html';
if(file_exists($root.'/COMPLETE'))exit;
$lock=fopen($root.'/deploy.lock','c');if(!flock($lock,LOCK_EX|LOCK_NB))exit;
if(file_exists($root.'/FAILED'))exit(1);
$backup=$root.'/rollback';@mkdir($backup,0700,true);
$mu=$web.'/wp-content/mu-plugins/anykey-roundtable-discovery.php';
$release_plugin_dir=$web.'/wp-content/plugins/anykey-roundtable-records';
$func=$web.'/wp-content/themes/anykey-phoenix/functions.php';
$changed=false;$post=0;
try{
 foreach(json_decode(file_get_contents($root.'/manifest.json'),true) as $name=>$hash){if(hash_file('sha256',$root.'/'.$name)!==$hash)throw new Exception('Payload mismatch: '.$name);}
 if(file_exists($mu)||file_exists($release_plugin_dir))throw new Exception('Release targets already exist; inspect before deployment');
 $original=file_get_contents($func);$old="            array('AI Round Table', 'ai-round-table'),\n";$anchor="        'Experiments' => array(\n";
 if(substr_count($original,$old)!==1||substr_count($original,$anchor)!==1)throw new Exception('Navigation guard mismatch');
 require $web.'/wp-load.php';
 if(home_url()!=='https://anykeycafe.com')throw new Exception('Unexpected site identity');
 if(get_page_by_path('session-006-buried-sky-audiobook-direction',OBJECT,'ak_rt_session'))throw new Exception('Existing session requires reconciliation');
 file_put_contents($backup.'/functions.php',$original);
 file_put_contents($backup.'/active-plugins.json',json_encode(get_option('active_plugins')));
 $updated=str_replace($old,'',$original);$updated=str_replace($anchor,$anchor."            array('Roundtable — Public Sessions', 'ai-round-table'),\n",$updated);
 umask(0022);
 $it=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root.'/anykey-roundtable-records',FilesystemIterator::SKIP_DOTS));
 foreach($it as $file){$rel=substr($file->getPathname(),strlen($root.'/anykey-roundtable-records/'));$target=$release_plugin_dir.'/'.$rel;@mkdir(dirname($target),0755,true);if(!copy($file->getPathname(),$target))throw new Exception('Copy failure');}
 $changed=true;
 require_once $web.'/wp-admin/includes/plugin.php';
 kses_remove_filters();
 $result=activate_plugin('anykey-roundtable-records/anykey-roundtable-records.php');if(is_wp_error($result))throw new Exception($result->get_error_message());
 $record=get_option('ak_rt_session_006_release');$post=(int)($record['post_id']??0);if(!$post||get_post_status($post)!=='publish')throw new Exception('Session activation failed');
 copy($root.'/anykey-roundtable-discovery.php',$mu);
 file_put_contents($func.'.release-tmp',$updated);rename($func.'.release-tmp',$func);
 flush_rewrite_rules();wp_cache_flush();
 file_put_contents($root.'/COMPLETE',json_encode(['time'=>gmdate('c'),'post_id'=>$post,'functions_before'=>hash('sha256',$original),'functions_after'=>hash_file('sha256',$func)],JSON_PRETTY_PRINT));
 echo "COMPLETE\n";
}catch(Throwable $e){
 if($changed){if(file_exists($mu))unlink($mu);copy($backup.'/functions.php',$func);deactivate_plugins('anykey-roundtable-records/anykey-roundtable-records.php');if($post)wp_delete_post($post,true);flush_rewrite_rules();}
 file_put_contents($root.'/FAILED',$e->getMessage());fwrite(STDERR,$e->getMessage()."\n");exit(1);
}
