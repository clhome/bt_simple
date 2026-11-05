# coding: utf-8
import os
import sys
import types
import unittest
import tempfile
import shutil
import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
for _p in (project_root, web_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_admin_pkg = types.ModuleType('admin')
_admin_pkg.__path__ = [os.path.join(web_dir, 'admin')]
sys.modules.setdefault('admin', _admin_pkg)

import core.yf as yf
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


def _generate_test_cert_pem(common_name='test.com', days=30, is_ecc=True, sans=None):
    if is_ecc:
        key = ec.generate_private_key(ec.SECP256R1())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Test Authority Org'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'Test CA Root')
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    before_delta = datetime.timedelta(days=abs(days) + 10)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(123456789)
        .not_valid_before(now - before_delta)
        .not_valid_after(now + datetime.timedelta(days=days))
    )

    if sans:
        san_list = [x509.DNSName(s) for s in sans]
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False
        )

    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')


class TestSslStatusAndCronFix(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='yf_ssl_test_')

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_get_cert_name_ecc_and_rsa(self):
        # 1. 测试 ECC 证书解析
        ecc_pem = _generate_test_cert_pem(common_name='ecc.yangmaok.com', days=60, is_ecc=True, sans=['ecc.yangmaok.com', '*.yangmaok.com'])
        ecc_file = os.path.join(self.tmp_dir, 'ecc_fullchain.pem')
        with open(ecc_file, 'w', encoding='utf-8') as f:
            f.write(ecc_pem)

        data = yf.getCertName(ecc_file)
        self.assertIsNotNone(data)
        self.assertEqual(data['issuer'], 'Test CA Root')
        self.assertEqual(data['issuer_o'], 'Test Authority Org')
        self.assertIn('ecc.yangmaok.com', data['dns'])
        self.assertIn('*.yangmaok.com', data['dns'])
        self.assertGreaterEqual(data['endtime'], 58)
        self.assertLessEqual(data['endtime'], 61)

        # 2. 测试直接传入 PEM 字符串
        data_str = yf.getCertName(ecc_pem)
        self.assertIsNotNone(data_str)
        self.assertEqual(data_str['subject'], 'ecc.yangmaok.com')

        # 3. 测试 RSA 证书解析
        rsa_pem = _generate_test_cert_pem(common_name='rsa.yangmaok.com', days=15, is_ecc=False)
        rsa_file = os.path.join(self.tmp_dir, 'rsa_fullchain.pem')
        with open(rsa_file, 'w', encoding='utf-8') as f:
            f.write(rsa_pem)

        data_rsa = yf.getCertName(rsa_file)
        self.assertIsNotNone(data_rsa)
        self.assertGreaterEqual(data_rsa['endtime'], 14)
        self.assertLessEqual(data_rsa['endtime'], 16)

        # 4. 测试非法内容与不存在文件安全防御
        self.assertIsNone(yf.getCertName(None))
        self.assertIsNone(yf.getCertName(''))
        self.assertIsNone(yf.getCertName(os.path.join(self.tmp_dir, 'not_exist.pem')))
        self.assertIsNone(yf.getCertName('invalid pem content'))

    def test_02_site_list_wildcard_ssl_extraction(self):
        # 模拟站点列表场景：vhost 配置引用泛域名证书路径
        wildcard_cert = _generate_test_cert_pem(common_name='*.yangmaok.com', days=45, sans=['*.yangmaok.com', 'yangmaok.com'])
        wildcard_path = os.path.join(self.tmp_dir, 'wildcard_fullchain.pem').replace('\\', '/')
        with open(wildcard_path, 'w', encoding='utf-8') as f:
            f.write(wildcard_cert)

        subdomain_conf = f"""server {{
    listen 80;
    listen 443 ssl;
    server_name h5.gqz.yangmaok.com;
    ssl_certificate    {wildcard_path};
    ssl_certificate_key  /dummy/path/privkey.pem;
}}"""

        # 验证正则提取逻辑
        import re
        cert_match = re.search(r"ssl_certificate\s+([^;\s]+);", subdomain_conf)
        self.assertIsNotNone(cert_match)
        extracted_path = cert_match.group(1).strip()
        self.assertEqual(extracted_path, wildcard_path)
        self.assertTrue(os.path.exists(extracted_path))

        parsed = yf.getCertName(extracted_path)
        self.assertIsNotNone(parsed)
        self.assertGreaterEqual(parsed['endtime'], 44)

    def test_03_expired_cert_endtime_calculation(self):
        # 验证已过期证书能够正确计算出负数剩余天数，不会抛异常
        expired_pem = _generate_test_cert_pem(common_name='expired.yangmaok.com', days=-5)
        parsed = yf.getCertName(expired_pem)
        self.assertIsNotNone(parsed)
        self.assertLess(parsed['endtime'], 0)

    def test_04_init_acme_cron_standard_command_and_self_healing(self):
        from admin.setup.init_cron import init_acme_cron
        name = "[勿删]ACME定时强制更新"

        # 1. 模拟存量系统中存在包含 --standalone 和 --force 的旧错误任务
        old_cmd = "/root/.acme.sh/acme.sh --cron --force --standalone"
        echo_id = "test_echo_123"
        cron_script_dir = os.path.join(self.tmp_dir, 'cron')
        os.makedirs(cron_script_dir, exist_ok=True)
        cron_script_file = os.path.join(cron_script_dir, echo_id)
        with open(cron_script_file, 'w', encoding='utf-8') as f:
            f.write(f"#!/bin/bash\n{old_cmd}\n")

        # Mock yf.M("crontab") 与 yf.getServerDir()
        fake_db_record = {'id': 99, 'name': name, 'sbody': old_cmd, 'echo': echo_id}
        updated_body = []

        class MockCrontabM:
            def field(self, f):
                return self
            def where(self, w, p):
                return self
            def find(self):
                return fake_db_record
            def save(self, data):
                updated_body.append(data.get('sbody'))
                fake_db_record['sbody'] = data.get('sbody')
                return True

        old_M = yf.M
        old_getServerDir = yf.getServerDir
        try:
            yf.M = lambda table: MockCrontabM() if table == 'crontab' else old_M(table)
            yf.getServerDir = lambda: self.tmp_dir.replace('\\', '/')

            # 触发自愈
            res = init_acme_cron()
            self.assertFalse(res)  # 存量记录已存在时返回 False

            # 验证数据库中的命令已被修复
            self.assertTrue(len(updated_body) > 0)
            fixed_cmd = updated_body[0]
            self.assertNotIn('--standalone', fixed_cmd)
            self.assertNotIn('--force', fixed_cmd)
            self.assertIn('--cron --home', fixed_cmd)

            # 验证物理脚本文件也已同步更新
            with open(cron_script_file, 'r', encoding='utf-8') as f:
                new_script_content = f.read()
            self.assertNotIn('--standalone', new_script_content)
            self.assertNotIn('--force', new_script_content)
            self.assertIn(fixed_cmd, new_script_content)
        finally:
            yf.M = old_M
            yf.getServerDir = old_getServerDir


if __name__ == '__main__':
    unittest.main()
