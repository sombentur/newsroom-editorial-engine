<?php
/**
 * Plugin Name: Newsroom SEO Bridge
 * Description: Minimal, secure REST route so the Newsroom Engine can persist Yoast / Rank Math SEO post meta over an authenticated Application Password connection. Exposes ONLY a fixed allow-list of SEO meta keys and enforces per-post edit capability. Does not modify WordPress core, themes, or other plugins.
 * Version: 1.0.0
 * Author: Newsroom Engine
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) { exit; }

add_action('rest_api_init', function () {

    // Health probe — lets the engine detect the plugin is installed.
    register_rest_route('newsroom/v1', '/ping', array(
        'methods'  => 'GET',
        'permission_callback' => function () { return current_user_can('edit_posts'); },
        'callback' => function () {
            return array('ok' => true, 'plugin' => 'newsroom-seo-bridge', 'version' => '1.0.0');
        },
    ));

    // Persist SEO meta for a single post.
    register_rest_route('newsroom/v1', '/post-seo', array(
        'methods' => WP_REST_Server::CREATABLE, // POST
        'permission_callback' => function ($request) {
            $post_id = absint($request['post_id']);
            if (!$post_id || !current_user_can('edit_post', $post_id)) {
                return new WP_Error('forbidden', 'You cannot edit this post.', array('status' => 403));
            }
            return true;
        },
        'args' => array(
            'post_id' => array('required' => true, 'sanitize_callback' => 'absint'),
            'meta'    => array('required' => true, 'type' => 'object'),
        ),
        'callback' => function ($request) {
            $post_id = absint($request['post_id']);
            $meta    = (array) $request['meta'];

            // Strict allow-list — no arbitrary meta may be written.
            $allowed = array(
                // Yoast SEO
                '_yoast_wpseo_title', '_yoast_wpseo_metadesc', '_yoast_wpseo_focuskw',
                '_yoast_wpseo_canonical', '_yoast_wpseo_opengraph-title',
                '_yoast_wpseo_opengraph-description', '_yoast_wpseo_twitter-title',
                '_yoast_wpseo_twitter-description',
                // Rank Math
                'rank_math_title', 'rank_math_description', 'rank_math_focus_keyword',
                'rank_math_canonical_url', 'rank_math_robots', 'rank_math_facebook_title',
                'rank_math_facebook_description', 'rank_math_twitter_title',
                'rank_math_twitter_description',
            );

            $updated = array();
            foreach ($meta as $key => $value) {
                if (!in_array($key, $allowed, true) || !is_string($value)) {
                    return new WP_Error('invalid_meta', 'Unsupported meta key or value: ' . $key, array('status' => 400));
                }
                update_post_meta($post_id, $key, sanitize_text_field($value));
                $updated[] = $key;
            }

            return array('post_id' => $post_id, 'updated' => $updated);
        },
    ));

    // Read the allow-listed SEO meta back for verification.
    register_rest_route('newsroom/v1', '/post-seo/(?P<id>\d+)', array(
        'methods' => 'GET',
        'permission_callback' => function ($request) {
            $post_id = absint($request['id']);
            return $post_id && current_user_can('edit_post', $post_id);
        },
        'callback' => function ($request) {
            $post_id = absint($request['id']);
            $keys = array(
                '_yoast_wpseo_title', '_yoast_wpseo_metadesc', '_yoast_wpseo_focuskw',
                'rank_math_title', 'rank_math_description', 'rank_math_focus_keyword',
            );
            $out = array();
            foreach ($keys as $k) {
                $v = get_post_meta($post_id, $k, true);
                if ($v !== '') { $out[$k] = $v; }
            }
            return array('post_id' => $post_id, 'meta' => $out);
        },
    ));
});
