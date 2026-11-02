<?php
/**
 * Plugin Name: AnyKey Roundtable Records
 * Description: Public-safe, versioned presentation records for completed AI Roundtable sessions.
 * Version: 0.3.2
 * Author: AnyKey Cafe
 */

if (!defined('ABSPATH')) {
    exit;
}

final class AnyKey_Roundtable_Records {
    private const POST_TYPE = 'ak_rt_session';
    private const VERSION = '0.3.2';

    public static function init(): void {
        add_action('init', array(__CLASS__, 'register_post_type'));
        add_action('wp_enqueue_scripts', array(__CLASS__, 'enqueue_assets'));
        add_shortcode('anykey_roundtable_archive', array(__CLASS__, 'archive_shortcode'));
        add_filter('the_content', array(__CLASS__, 'append_archive_to_roundtable_page'), 25);
        add_filter('document_title_parts', array(__CLASS__, 'single_title'));
    }

    public static function register_post_type(): void {
        register_post_type(self::POST_TYPE, array(
            'labels' => array(
                'name' => 'Roundtable Records',
                'singular_name' => 'Roundtable Record',
                'add_new_item' => 'Add Roundtable Record',
                'edit_item' => 'Edit Roundtable Record',
                'view_item' => 'View Roundtable Record',
            ),
            'public' => true,
            'show_in_rest' => true,
            'has_archive' => 'roundtable-records',
            'rewrite' => array('slug' => 'roundtable-record'),
            'menu_icon' => 'dashicons-groups',
            'supports' => array('title', 'editor', 'excerpt', 'revisions', 'custom-fields'),
            'show_in_nav_menus' => false,
        ));

        foreach (array(
            'ak_rt_round_id',
            'ak_rt_session_number',
            'ak_rt_status',
            'ak_rt_date',
            'ak_rt_participants',
            'ak_rt_duration',
            'ak_rt_result',
            'ak_rt_transcript_hash',
            'ak_rt_derivative_version',
            'ak_rt_public_safety',
        ) as $key) {
            register_post_meta(self::POST_TYPE, $key, array(
                'type' => 'string',
                'single' => true,
                'show_in_rest' => true,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback' => static function (): bool {
                    return current_user_can('edit_posts');
                },
            ));
        }
    }

    public static function activate(): void {
        self::register_post_type();
        $siteurl = get_option('siteurl');
        $home = get_option('home');
        $local_mirror = getenv('AK_RT_ALLOW_LOCAL_MIRROR') === '1'
            && $siteurl === 'http://127.0.0.1:8899'
            && $home === 'http://127.0.0.1:8899';
        if (!$local_mirror && ($siteurl !== 'https://anykeycafe.com' || $home !== 'https://anykeycafe.com')) {
            throw new RuntimeException('Roundtable Records activation refused: unexpected site identity.');
        }

        $seed_path = plugin_dir_path(__FILE__) . 'seed/session-006.json';
        if (!is_readable($seed_path)) {
            throw new RuntimeException('The reviewed Session 006 derivative is missing.');
        }
        $record = json_decode((string) file_get_contents($seed_path), true, 512, JSON_THROW_ON_ERROR);
        $round_id = '1c15b091-4c9e-430d-8529-4c7f2ab3f7aa';
        if (($record['schema'] ?? '') !== 'anykey.roundtable.public-derivative.v1'
            || ($record['source']['round_id'] ?? '') !== $round_id
            || ($record['derivative_version'] ?? '') !== '1.0.0'
            || empty($record['post'])
            || empty($record['meta'])) {
            throw new RuntimeException('The Session 006 derivative failed its identity check.');
        }
        $content = (string) ($record['post']['post_content'] ?? '');
        foreach (array('memory:', '/home/', '192.168.', '127.0.0.1', 'participant_prompt') as $forbidden) {
            if (stripos($content, $forbidden) !== false) {
                throw new RuntimeException('Private marker found in public derivative: ' . $forbidden);
            }
        }

        $existing = get_posts(array(
            'post_type' => self::POST_TYPE,
            'post_status' => 'any',
            'meta_key' => 'ak_rt_round_id',
            'meta_value' => $round_id,
            'numberposts' => 1,
            'fields' => 'ids',
        ));
        $post = $record['post'];
        $post['ID'] = $existing ? (int) $existing[0] : 0;
        $post['post_type'] = self::POST_TYPE;
        $post['post_status'] = 'publish';
        $post_id = wp_insert_post(wp_slash($post), true);
        if (is_wp_error($post_id)) {
            throw new RuntimeException($post_id->get_error_message());
        }
        foreach ($record['meta'] as $key => $value) {
            if (strpos((string) $key, 'ak_rt_') === 0) {
                update_post_meta((int) $post_id, sanitize_key((string) $key), sanitize_text_field((string) $value));
            }
        }
        update_option('ak_rt_session_006_release', array(
            'post_id' => (int) $post_id,
            'round_id' => $round_id,
            'derivative_version' => '1.0.0',
            'derivative_sha256' => hash_file('sha256', $seed_path),
            'activated_at_gmt' => gmdate('c'),
            'created_new_post' => !$existing,
        ), false);
        clean_post_cache((int) $post_id);
        flush_rewrite_rules();
    }

    public static function deactivate(): void {
        flush_rewrite_rules();
    }

    public static function enqueue_assets(): void {
        if (is_singular(self::POST_TYPE) || is_post_type_archive(self::POST_TYPE) || is_page('ai-round-table')) {
            wp_enqueue_style(
                'anykey-roundtable-records',
                plugin_dir_url(__FILE__) . 'assets/roundtable-records.css',
                array(),
                self::VERSION
            );
        }
    }

    public static function append_archive_to_roundtable_page(string $content): string {
        if (!is_page('ai-round-table') || !in_the_loop() || !is_main_query()) {
            return $content;
        }
        if (has_shortcode($content, 'anykey_roundtable_archive')) {
            return $content;
        }
        return $content . do_shortcode('[anykey_roundtable_archive]');
    }

    public static function archive_shortcode(): string {
        $records = new WP_Query(array(
            'post_type' => self::POST_TYPE,
            'post_status' => 'publish',
            'posts_per_page' => 20,
            'orderby' => array('date' => 'DESC', 'ID' => 'DESC'),
            'no_found_rows' => true,
        ));

        ob_start();
        ?>
        <section class="ak-rt-archive" aria-labelledby="ak-rt-archive-title">
            <header class="ak-rt-archive__header">
                <p class="ak-rt-eyebrow">THE WORKING RECORD</p>
                <h2 id="ak-rt-archive-title">Sessions at the table</h2>
                <p>These are frozen, public-safe derivatives of private append-only records. They preserve the question, attributable positions, disagreement, limitations, and disposition without exposing private prompts or memory context.</p>
            </header>
            <?php if (!$records->have_posts()) : ?>
                <p class="ak-rt-empty">The table is prepared. Its first public record will appear here.</p>
            <?php else : ?>
                <div class="ak-rt-grid">
                    <?php while ($records->have_posts()) : $records->the_post(); ?>
                        <?php
                        $post_id = get_the_ID();
                        $session = get_post_meta($post_id, 'ak_rt_session_number', true);
                        $status = get_post_meta($post_id, 'ak_rt_status', true) ?: 'Recorded';
                        $date = get_post_meta($post_id, 'ak_rt_date', true) ?: get_the_date('F j, Y');
                        $participants = get_post_meta($post_id, 'ak_rt_participants', true);
                        $duration = get_post_meta($post_id, 'ak_rt_duration', true);
                        $result = get_post_meta($post_id, 'ak_rt_result', true);
                        ?>
                        <article class="ak-rt-card">
                            <div class="ak-rt-card__topline">
                                <span class="ak-rt-status"><?php echo esc_html($status); ?></span>
                                <span><?php echo $session ? esc_html('Session ' . $session . ' · ') : ''; ?><time><?php echo esc_html($date); ?></time></span>
                            </div>
                            <h3><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h3>
                            <?php if (has_excerpt()) : ?><div class="ak-rt-card__summary"><?php the_excerpt(); ?></div><?php endif; ?>
                            <?php if ($result) : ?><p class="ak-rt-card__result"><strong>Outcome:</strong> <?php echo esc_html($result); ?></p><?php endif; ?>
                            <dl class="ak-rt-facts">
                                <?php if ($participants) : ?><div><dt>At the table</dt><dd><?php echo esc_html($participants); ?></dd></div><?php endif; ?>
                                <?php if ($duration) : ?><div><dt>Runtime</dt><dd><?php echo esc_html($duration); ?></dd></div><?php endif; ?>
                            </dl>
                            <a class="ak-rt-card__link" href="<?php the_permalink(); ?>">Open the public record <span aria-hidden="true">&rarr;</span></a>
                        </article>
                    <?php endwhile; ?>
                </div>
            <?php endif; ?>
        </section>
        <?php
        wp_reset_postdata();
        return (string) ob_get_clean();
    }

    public static function single_title(array $parts): array {
        if (is_singular(self::POST_TYPE)) {
            $parts['site'] = 'AnyKey Cafe Roundtable';
        }
        return $parts;
    }
}

AnyKey_Roundtable_Records::init();
register_activation_hook(__FILE__, array('AnyKey_Roundtable_Records', 'activate'));
register_deactivation_hook(__FILE__, array('AnyKey_Roundtable_Records', 'deactivate'));
