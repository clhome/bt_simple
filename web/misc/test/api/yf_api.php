<?php
/**
 * YF API鎺ュ彛绀轰緥Demo
 * 浠呬緵鍙傝€冿紝璇锋牴鎹疄闄呴」鐩渶姹傚紑鍙戯紝骞跺仛濂藉畨鍏ㄥ鐞?
 * date 2022-11-28
 * author midoks
 */
class yfApi {
	private $YF_PANEL      = "http://127.0.0.1:64307"; //闈㈡澘鍦板潃
	private $YF_APP_ID     = 'hC6XArWzRY';
	private $YF_APP_SERECT = 'NSGaFhMWyaN5Yi3ftTkZ';

	//濡傛灉甯屾湜澶氬彴闈㈡澘锛屽彲浠ュ湪瀹炰緥鍖栧璞℃椂锛屽皢闈㈡澘鍦板潃涓庡瘑閽ヤ紶鍏?
	public function __construct($YF_panel = null, $app_id = null, $app_secret = null) {
		if ($YF_panel) {
			$this->MW_PANEL = $YF_panel;
		}

		if ($app_id) {
			$this->MW_APP_ID = $app_id;
		}

		if ($app_secret) {
			$this->MW_APP_SERECT = $app_secret;
		}
	}

	/**
	 * 鍙戣捣POST璇锋眰
	 * @param String $url 鐩爣缃戝～锛屽甫http://
	 * @param Array|String $data 娆叉彁浜ょ殑鏁版嵁
	 * @return string
	 */
	private function httpPost($url, $data, $timeout = 60) {

		$ch = curl_init();
		// 璁剧疆澶撮儴淇℃伅
		$headers = [
			'app-id: ' . $this->MW_APP_ID,
			'app-secret: ' . $this->MW_APP_SERECT,
		];
		curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
		curl_setopt($ch, CURLOPT_URL, $url);
		curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
		curl_setopt($ch, CURLOPT_POST, 1);
		curl_setopt($ch, CURLOPT_POSTFIELDS, $data);
		curl_setopt($ch, CURLOPT_COOKIEJAR, $cookie_file);
		curl_setopt($ch, CURLOPT_COOKIEFILE, $cookie_file);
		curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
		curl_setopt($ch, CURLOPT_HEADER, 0);
		curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
		curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
		$output = curl_exec($ch);
		curl_close($ch);
		return $output;
	}

	public function panel($endpoint, $data) {
		$url = $this->MW_PANEL . $endpoint;
		return $this->httpPost($url, $data);
	}

	//绀轰緥鍙栭潰鏉挎棩蹇?
	public function getLogsList() {
		$post_data['p']     = '1';
		$post_data['limit'] = 10;

		//璇锋眰闈㈡澘鎺ュ彛
		$data = $this->panel('/logs/get_log_list', $post_data);

		//瑙ｆ瀽JSON鏁版嵁
		// $data = json_decode($result, true);
		return $data;
	}

}

//瀹炰緥鍖栧璞?
$api = new yfApi();
//鑾峰彇闈㈡澘鏃ュ織
$rdata = $api->getLogsList();

// var_dump($rdata);
//杈撳嚭JSON鏁版嵁鍒版祻瑙堝櫒
echo json_encode($rdata);

?>
