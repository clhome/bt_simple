import re
with open(r'f:\git\gitea20250909\bt_simple\plugins\op_waf\js\op_waf.js', 'r', encoding='utf-8') as f:
    text = f.read()

marker = '                        getIpv4Address(function(rdata){'
idx1 = text.find(marker)
idx2 = text.find('function wafGloablRefresh')

if idx1 != -1 and idx2 != -1:
    before = text[:idx1 + len(marker) + 1]
    after = text[idx2:]
    
    missing_code = '''                            var tbody = ''
                            for (var i = 0; i < rdata.length; i++) {
                                tbody += '<tr>\\
                                        <td>'+ rdata[i][0].join('.') + '</td>\\
                                        <td>'+ rdata[i][1].join('.') + '</td>\\
                                        <td class="text-right"><a class="btlink" onclick="removeIpBlack('+ i + ')">删除</a></td>\\
                                    </tr>'
                            }
                            $("#ip_black_con").html(tbody);
                        });
                    }else{
                        $('.ipv4_block').hide().next().show();
                        getIpv6Address(function(res){
                            var tbody = '',rdata = res;
                            for (var i = 0; i < rdata.length; i++) {
                                tbody += '<tr>\\
                                    <td>'+ rdata[i] + '</td>\\
                                    <td class="text-right"><a class="btlink" onclick="removeIpv6Black(\\''+ rdata[i] + '\\')">删除</a></td>\\
                                </tr>'
                            }
                            $("#ipv6_black_con").html(tbody);
                        });
                    }
                });
                $('.btn_add_ipv6').click(function(){
                    var ipv6 = $('[name="ipv6_address"]').val();
                    addIpv6Req(ipv6, function(res){
                        layer.msg(res.msg,{icon:res.status?1:2});
                        if(res.status){
                            $('[name="ipv6_address"]').val('');
                            $('.tab_list .tab_block:eq(1)').click();
                        }
                    });
                });
                $('.tab_list .tab_block:eq(0)').click();
            }
        });
        tableFixed("ipBlack");
    } else {
        $('.tab_list .tab_block:eq(0)').click();
    }
}

function wafScreen(){

    owPost('waf_srceen', {}, function(data){
        var rdata = $.parseJSON(data.data);

        var end_time = Date.now();
        var cos_time = (end_time/1000) - parseInt(rdata['start_time']);
        var cos_day = parseInt(parseInt(cos_time)/86400);

        var css = `<style>
            .waf-dashboard { padding: 5px 15px 15px 5px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; animation: wafFadeIn 0.4s ease; }
            @keyframes wafFadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            
            .waf-top-cards { display: flex; gap: 20px; margin-bottom: 25px; }
            .waf-card-primary, .waf-card-info {
                flex: 1; border-radius: 12px; padding: 25px 20px; color: #fff; text-align: center;
                box-shadow: 0 8px 20px rgba(0,0,0,0.1); position: relative; overflow: hidden;
                transition: transform 0.3s ease;
            }
            .waf-card-primary:hover, .waf-card-info:hover { transform: translateY(-2px); }
            .waf-card-primary { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
            .waf-card-info { background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); }
            .waf-card-title { font-size: 15px; opacity: 0.9; margin-bottom: 5px; font-weight: 500; letter-spacing: 1px; }
            .waf-card-val { font-size: 40px; font-weight: 700; line-height: 1.1; font-family: Arial, sans-serif; }
            
            .waf-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }
            .waf-stat-box { 
                background: #fff; border: 1px solid #edf2f9; border-radius: 10px; padding: 20px 10px;
                text-align: center; transition: all 0.3s ease; box-shadow: 0 2px 6px rgba(227,233,243,0.5);
                position: relative; overflow: hidden;
            }
            .waf-stat-box::after { content: ''; position: absolute; left: 0; bottom: 0; width: 100%; height: 3px; background: #3b82f6; transform: scaleX(0); transition: transform 0.3s ease; transform-origin: left; }
            .waf-stat-box:hover::after { transform: scaleX(1); }
            .waf-stat-box:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(200,210,230,0.7); border-color: transparent; }
            .waf-stat-name { font-size: 13px; color: #6b7280; margin-bottom: 8px; font-weight: 600; }
            .waf-stat-val { font-size: 26px; color: #111827; font-weight: 700; font-family: Arial, sans-serif; }
            
            .waf-help-list { background: #f0fdf4; border-left: 4px solid #10b981; padding: 18px 25px; border-radius: 6px; color: #374151; list-style-type: none; margin:0; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
            .waf-help-list li { margin-bottom: 10px; font-size: 13px; position: relative; padding-left: 18px; line-height: 1.5; }
            .waf-help-list li:before { content: '\\u2713'; position: absolute; left: 0; color: #10b981; font-weight: bold; font-size: 14px; }
            .waf-help-list li:last-child { margin-bottom: 0; }
        </style>`;

        var con = css + '<div class="waf-dashboard">';
        
        con += '<div class="waf-top-cards">\\
            <div class="waf-card-primary">\\
                <div class="waf-card-title">总拦截 (次)</div>\\
                <div class="waf-card-val">' + rdata.total + '</div>\\
            </div>\\
            <div class="waf-card-info">\\
                <div class="waf-card-title">安全防护 (天)</div>\\
                <div class="waf-card-val">' + cos_day + '</div>\\
            </div>\\
        </div>';

        con += '<div class="waf-grid">\\
            <div class="waf-stat-box"><div class="waf-stat-name">POST渗透</div><div class="waf-stat-val">' + rdata.rules.post + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">GET渗透</div><div class="waf-stat-val">' + rdata.rules.args + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">CC攻击</div><div class="waf-stat-val">' + rdata.rules.cc + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">恶意User-Agent</div><div class="waf-stat-val">' + rdata.rules.user_agent + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">Cookie渗透</div><div class="waf-stat-val">' + rdata.rules.cookie + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">恶意扫描</div><div class="waf-stat-val">' + rdata.rules.scan + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">恶意HEAD请求</div><div class="waf-stat-val">0</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">URI自定义拦截</div><div class="waf-stat-val">' + rdata.rules.url + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">URI保护</div><div class="waf-stat-val">' + rdata.rules.args + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">恶意文件上传</div><div class="waf-stat-val">' + rdata.rules.upload_ext + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">禁止的扩展名</div><div class="waf-stat-val">' + rdata.rules.path + '</div></div>\\
            <div class="waf-stat-box"><div class="waf-stat-name">禁止PHP脚本</div><div class="waf-stat-val">' + rdata.rules.php_path + '</div></div>\\
        </div>';

        con += '<ul class="waf-help-list">\\
            <li>在此处关闭防火墙后，所有站点将失去保护</li>\\
            <li>网站防火墙会使nginx有一定的性能损失（&lt;5% 10C静态并发测试结果）</li>\\
            <li>网站防火墙主要针对网站渗透攻击，暂时不具备系统加固功能</li>\\
        </ul></div>';

        $(".soft-man-con").html(con);
    });
}
\n'''
    
    with open(r'f:\git\gitea20250909\bt_simple\plugins\op_waf\js\op_waf.js', 'w', encoding='utf-8') as f:
        f.write(before + missing_code + after)
    print('Fixed op_waf.js')
else:
    print('Failed to find markers')
