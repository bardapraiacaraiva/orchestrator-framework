#!/usr/bin/env python3
"""Create batch test tasks for skills testing."""
from db import DB

db = DB()

tasks = [
    # MARKETING (5)
    ("TEST-ADS", "Blueprint ads Meta+Google Vivenda",
     "Criar blueprint de campanhas pagas para Vivenda Creative Home. Plataformas: Meta Ads (Instagram+Facebook) e Google Ads. Budget mensal: 500 EUR. Objectivo: gerar leads qualificados (pedidos de orcamento). Incluir: estrutura de campanhas, audiences, copies, budget split, KPIs.",
     "dario-ads-blueprint", "worker-ads"),
    ("TEST-PIPE", "Pipeline de vendas Vivenda Creative Home",
     "Desenhar pipeline de vendas completo para Vivenda Creative Home. Etapas desde contacto inicial ate fecho. Lead scoring, automacoes, follow-up cadences. Ferramenta sugerida: HubSpot ou Pipedrive. Ticket medio: 5000-15000 EUR.",
     "dario-pipeline", "worker-pipeline"),
    ("TEST-SOCIAL", "Estrategia redes sociais Vivenda",
     "Estrategia completa de redes sociais para Vivenda Creative Home. Plataformas: Instagram, Pinterest, LinkedIn. Pilares de conteudo, calendario semanal, formatos, hashtags, 10 ideias de posts prontas. Tom: sofisticado, Lisboa lifestyle.",
     "dario-social", "worker-social"),
    ("TEST-CONTENT", "Content strategy authority Vivenda",
     "Plano de conteudo para posicionar Vivenda Creative Home como autoridade em design de interiores Lisboa. Pillar pages, clusters, blog, lead magnets, video. Calendario 90 dias. Keywords target.",
     "dario-content", "worker-content"),
    ("TEST-PROPOSAL", "Proposta comercial Vivenda para cliente",
     "Criar proposta comercial profissional da Vivenda Creative Home para um cliente ficticio: casal portugues, apartamento T3 no Principe Real, 120m2, budget 40000 EUR para remodelacao completa. Incluir: escopo, metodologia, timeline, equipa, preco, garantias.",
     "dario-proposal", "worker-proposal"),
    # SEO (6)
    ("TEST-TECH", "Technical SEO audit vivendacreative.pt",
     "Auditoria tecnica SEO completa de vivendacreative.pt (WordPress). Crawlability, indexability, Core Web Vitals, mobile, JS rendering, internal linking, redirects, structured data. Fix priority matrix.",
     "seo-technical", "worker-seo-technical"),
    ("TEST-SCONT", "SEO content audit vivendacreative.pt",
     "Auditoria de conteudo SEO para vivendacreative.pt. E-E-A-T signals, keyword optimization, content depth, readability, internal linking, featured snippets, thin content. Content briefs para as 5 paginas mais importantes.",
     "seo-content", "worker-seo-content"),
    ("TEST-GEO", "GEO AI search optimization Vivenda",
     "Optimizacao para motores de busca IA (Google AI Overviews, ChatGPT, Perplexity, Bing Copilot). Analisar: acessibilidade crawlers IA, llms.txt, citabilidade, brand mentions, entity recognition. Recomendacoes especificas para vivendacreative.pt.",
     "seo-geo", "worker-seo-geo"),
    ("TEST-SMAP", "Sitemap architecture vivendacreative.pt",
     "Gerar sitemap XML completo para vivendacreative.pt. Incluir: sitemap index, image sitemap, prioridades e changefreq correctos, robots.txt. Codigo XML pronto a usar. Instrucoes Search Console.",
     "seo-sitemap", "worker-seo-sitemap"),
    ("TEST-IMG", "Image SEO audit vivendacreative.pt",
     "Auditoria de imagens SEO para vivendacreative.pt. Alt text, file names, formatos (WebP), lazy loading, responsive images, OG images, compressao. Alt text optimizado para 20 imagens tipo de um site de design interiores.",
     "seo-images", "worker-seo-images"),
    ("TEST-HREF", "Hreflang implementation PT/EN Vivenda",
     "Implementacao hreflang para vivendacreative.pt (PT) com futura versao EN. Tags para todas as paginas principais, x-default, self-referencing, XML sitemap hreflang. Codigo pronto a copiar.",
     "seo-hreflang", "worker-seo-hreflang"),
    # DIVA (6)
    ("TEST-MOOD", "Moodboard apartamento T3 Principe Real",
     "Moodboard completo para remodelacao de apartamento T3, 120m2, Principe Real Lisboa. Estilo: contemporaneo com toques portugueses. Paleta de cores, materiais, mobiliario, iluminacao, referencias visuais. Casal 35-40 anos, profissionais.",
     "diva-moodboard", "worker-diva-moodboard"),
    ("TEST-MAT", "Especificacao materiais remodelacao T3",
     "Especificacao tecnica de materiais para remodelacao T3 Principe Real: pavimentos, revestimentos WC e cozinha, bancadas, caixilharia, portas interiores. Propriedades tecnicas, precos PT, fornecedores, codigos ProNIC.",
     "diva-materials", "worker-diva-materials"),
    ("TEST-FLOOR", "Optimizacao planta T3 120m2",
     "Analisar e optimizar planta de apartamento T3, 120m2. Distribuicao actual: sala 30m2, cozinha 12m2, suite 16m2, quarto 12m2, quarto 10m2, WC suite 5m2, WC social 4m2, hall 6m2, corredor 5m2, varanda 8m2. Propor alternativas com melhor circulacao e uso de espaco.",
     "diva-floor-plan", "worker-diva-floor-plan"),
    ("TEST-BUDGET", "Orcamento remodelacao T3 Principe Real",
     "Orcamento detalhado para remodelacao completa de T3, 120m2, Principe Real Lisboa. Demolicoes, electricidade, canalizacao, pavimentos, revestimentos, cozinha, WCs, pintura, mobiliario fixo. Precos ProNIC/CYPE. IVA. Cenarios low/medium/high.",
     "diva-budget", "worker-diva-budget"),
    ("TEST-TIME", "Timeline obra remodelacao T3",
     "Cronograma detalhado para remodelacao T3, 120m2, Principe Real. Fases: projecto+licenciamento, demolicoes, toscos, instalacoes, acabamentos, mobiliario. Dependencias, caminho critico, marcos, prazos tipicos Camara Municipal Lisboa.",
     "diva-timeline", "worker-diva-timeline"),
    ("TEST-LIC", "Licenciamento camarario remodelacao T3",
     "Guia completo de licenciamento para remodelacao interior de T3 em Lisboa (Principe Real). Tipo de licenca necessaria, documentos, equipa tecnica, taxas CML, prazos tipicos. Artigos RJUE relevantes. Casos que dispensam licenca.",
     "diva-licensing", "worker-diva-licensing"),
    # OPERATIONS (4)
    ("TEST-LEGAL", "Contrato prestacao servicos Vivenda",
     "Minutar contrato de prestacao de servicos de design de interiores entre Vivenda Creative Home e cliente. Clausulas: escopo, prazo, preco, pagamentos, propriedade intelectual, confidencialidade, rescisao, foro. Direito portugues.",
     "dario-legal", "worker-legal"),
    ("TEST-HR", "Plano contratacao designer junior Vivenda",
     "Plano de contratacao para designer de interiores junior na Vivenda Creative Home. Job description, perfil, canais de recrutamento, processo seleccao, pacote salarial (benchmarks PT), onboarding 30/60/90 dias. Codigo do Trabalho.",
     "dario-hr", "worker-hr"),
    ("TEST-ONBOARD", "Onboarding cliente Vivenda Creative Home",
     "Experiencia de onboarding para novos clientes Vivenda. Welcome kit, emails, kickoff meeting agenda, documento de expectativas, milestones 30/60/90, feedback points, escalation. Reduzir time-to-value.",
     "dario-client-onboard", "worker-client-onboard"),
    ("TEST-PROD", "Estrategia produto servico design Vivenda",
     "Estrategia de produto/servico para Vivenda Creative Home. Analise mercado design interiores Lisboa, personas, value proposition, pacotes de servicos (consultoria/projecto/full), pricing, go-to-market, KPIs.",
     "dario-produto", "worker-product"),
]

for tid, title, desc, skill, worker in tasks:
    with db._conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tasks
            (id, title, description, project, skill, priority, status, assignee,
             execution_policy, dispatch_reason, created_at, assigned_at)
            VALUES (?, ?, ?, 'vivenda-test', ?, 'medium', 'todo', ?,
             'default', ?, datetime('now'), datetime('now'))""",
            (tid, title, desc, skill, worker, f"test execution {skill}"),
        )
        conn.commit()
    print(f"  {tid:<14} {skill}")

print(f"\n{len(tasks)} tasks criadas.")
