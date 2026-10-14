<?php
/**
 * Plugin Name: AnyKey Little Oogway Atlas
 * Description: Styles and installs the public memory-map feature on the Little Oogway page.
 * Version: 1.0.6
 * Author: AnyKey Cafe
 */

if (!defined('ABSPATH')) {
    exit;
}

const AKLOA_VERSION = '1.0.6';
const AKLOA_IMAGE_SHA256 = 'b4d80a3dce16e4f6514d8f7e48201a533bb0bf3e4d9e2f8eb51fa78ca84fa659';
const AKLOA_RESULT = 'anykey_little_oogway_atlas_result_v1';

function akloa_image_destination(): string {
    $uploads = wp_upload_dir(null, false);
    return trailingslashit((string) $uploads['basedir']) . '2026/10/little-oogway-memory-field-map.jpg';
}

function akloa_activate(): void {
    try {
        $source = __DIR__ . '/assets/little-oogway-memory-field-map.jpg';
        $destination = akloa_image_destination();
        if (!is_file($source) || hash_file('sha256', $source) !== AKLOA_IMAGE_SHA256) {
            throw new RuntimeException('The reviewed Atlas image is missing or does not match its release checksum.');
        }
        if (!wp_mkdir_p(dirname($destination))) {
            throw new RuntimeException('Could not create the Atlas image directory.');
        }
        $temporary = $destination . '.anykey-atlas-tmp';
        if (!copy($source, $temporary) || !rename($temporary, $destination)) {
            @unlink($temporary);
            throw new RuntimeException('Could not install the Atlas image.');
        }
        @chmod($destination, 0644);
        if (hash_file('sha256', $destination) !== AKLOA_IMAGE_SHA256) {
            throw new RuntimeException('The installed Atlas image failed verification.');
        }
        update_option(AKLOA_RESULT, array(
            'version' => AKLOA_VERSION,
            'completed_at' => current_time('mysql'),
            'image' => $destination,
            'sha256' => AKLOA_IMAGE_SHA256,
        ), false);
    } catch (Throwable $error) {
        update_option(AKLOA_RESULT, array('version' => AKLOA_VERSION, 'error' => $error->getMessage()), false);
        throw $error;
    }
}
register_activation_hook(__FILE__, 'akloa_activate');

function akloa_enqueue(): void {
    wp_enqueue_style('anykey-little-oogway-atlas', plugins_url('assets/atlas.css', __FILE__), array(), AKLOA_VERSION);
}
add_action('wp_enqueue_scripts', 'akloa_enqueue');

function akloa_feature_markup(): string {
    return <<<'HTML'
<aside id="memory-landscape" class="ak-memory-landscape" aria-labelledby="ak-memory-landscape-title"><div class="ak-memory-landscape__copy"><p class="ak-memory-landscape__kicker">FIRST PUBLIC MEMORY MAP · OCTOBER 2026</p><h3 id="ak-memory-landscape-title">Memory becomes landscape.</h3><p>Two thousand fragments from the public AnyKeyCafe archive, arranged by semantic similarity. Each point is a passage Little Ougway has absorbed; nearby points share language, subjects, and recurring patterns.</p><p>Open the living map to zoom, explore neighborhoods, and watch the archive organize itself.</p><p class="ak-memory-landscape__privacy">Public material only · No private conversations, local files, or internal identifiers</p><a class="ak-memory-landscape__button" href="https://atlas.nomic.ai/data/dgr1962/little-oogway-public-anykeycafe-memory-field/map" target="_blank" rel="noopener">Explore the live memory map <span aria-hidden="true">↗</span></a></div><figure class="ak-memory-landscape__figure"><a href="https://atlas.nomic.ai/data/dgr1962/little-oogway-public-anykeycafe-memory-field/map" target="_blank" rel="noopener"><img src="/wp-content/uploads/2026/10/little-oogway-memory-field-map.jpg" alt="Nomic Atlas semantic map of 2,000 public AnyKeyCafe memory fragments" loading="lazy" decoding="async"/></a><figcaption>Little Ougway’s first public memory field · 2,000 fragments · 768-dimensional embeddings</figcaption></figure></aside>
HTML;
}

function akloa_insert_feature(string $content): string {
    if (is_admin() || (int) get_the_ID() !== 894 || str_contains($content, 'ak-memory-landscape')) {
        return $content;
    }
    $heading = '<h3>What is working now</h3>';
    if (!str_contains($content, $heading)) {
        return $content;
    }
    return str_replace($heading, akloa_feature_markup() . $heading, $content);
}
add_filter('the_content', 'akloa_insert_feature', 12);

/**
 * Keep the established Little Ougway permalink available if the hosting
 * rewrite layer momentarily fails to resolve this one published page.
 */
function akloa_resolve_little_oogway_route($preempt, WP_Query $query) {
    if ($preempt !== false) {
        return $preempt;
    }

    global $wp;
    $request = isset($wp->request) ? trim((string) $wp->request, '/') : '';
    if ($request !== 'little-ougway') {
        return $preempt;
    }

    $page = get_page_by_path('little-ougway', OBJECT, 'page');
    if (!$page instanceof WP_Post || $page->post_status !== 'publish') {
        return $preempt;
    }

    $query->posts = array($page);
    $query->post = $page;
    $query->post_count = 1;
    $query->found_posts = 1;
    $query->max_num_pages = 1;
    $query->queried_object = $page;
    $query->queried_object_id = (int) $page->ID;
    $query->is_404 = false;
    $query->is_page = true;
    $query->is_singular = true;
    $query->is_home = false;
    $query->set('page_id', (int) $page->ID);
    status_header(200);

    return true;
}
add_filter('pre_handle_404', 'akloa_resolve_little_oogway_route', 10, 2);

function akloa_recover_little_oogway_template(): void {
    $path = isset($_SERVER['REQUEST_URI'])
        ? trim((string) parse_url((string) $_SERVER['REQUEST_URI'], PHP_URL_PATH), '/')
        : '';
    if ($path !== 'little-oogway' || !is_404()) {
        return;
    }

    $page = get_post(894);
    if (!$page instanceof WP_Post || $page->post_type !== 'page'
        || $page->post_name !== 'little-ougway' || $page->post_status !== 'publish'
    ) {
        return;
    }

    global $wp_query, $post;
    $post = $page;
    $wp_query->posts = array($page);
    $wp_query->post = $page;
    $wp_query->post_count = 1;
    $wp_query->found_posts = 1;
    $wp_query->max_num_pages = 1;
    $wp_query->queried_object = $page;
    $wp_query->queried_object_id = (int) $page->ID;
    $wp_query->is_404 = false;
    $wp_query->is_page = true;
    $wp_query->is_singular = true;
    $wp_query->is_home = false;
    $wp_query->query_vars['page_id'] = (int) $page->ID;
    setup_postdata($post);
    status_header(200);
}
add_action('template_redirect', 'akloa_recover_little_oogway_template', 0);

function akloa_notice(): void {
    if (!current_user_can('manage_options')) {
        return;
    }
    $result = get_option(AKLOA_RESULT);
    if (!is_array($result)) {
        return;
    }
    if (!empty($result['error'])) {
        echo '<div class="notice notice-error"><p><strong>Little Ougway Atlas stopped:</strong> ' . esc_html((string) $result['error']) . '</p></div>';
        return;
    }
    echo '<div class="notice notice-success is-dismissible"><p><strong>Little Ougway Atlas assets are ready.</strong> The public map image and page-only styling were installed and verified.</p></div>';
}
add_action('admin_notices', 'akloa_notice');
