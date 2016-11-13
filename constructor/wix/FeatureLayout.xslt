<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="2.0"
    xmlns:wix="http://schemas.microsoft.com/wix/2006/wi"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    exclude-result-prefixes="wix"
    >

  <xsl:output method="xml" indent="yes"/>

  <xsl:template match="wix:Wix/wix:Fragment">
    <xsl:copy copy-namespaces="no">
      <xsl:apply-templates select="@* | node()"/>
      <xsl:for-each select="wix:DirectoryRef/wix:Directory">
        <xsl:text>&#xd;&#xa;        </xsl:text> 
        <wix:ComponentGroup>
          <xsl:attribute name="Id">
            <xsl:choose>
              <xsl:when test="contains(@Name, 'vs2008_runtime') or contains(@Name, 'vs2010_runtime') or contains(@Name, 'vs2015_runtime')">
                <xsl:value-of select="'MSVC'"/>
              </xsl:when>
              <xsl:otherwise>
                <xsl:call-template name="idFromName">
                  <xsl:with-param name="pText" select="@Name"/>
                </xsl:call-template>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:attribute>
          <xsl:for-each select="descendant::wix:Component">
            <xsl:text>&#xd;&#xa;            </xsl:text> 
            <wix:ComponentRef Id="{@Id}"/>
          </xsl:for-each>
        <xsl:text>&#xd;&#xa;        </xsl:text> 
        </wix:ComponentGroup>
      </xsl:for-each>
      <xsl:text>&#xd;&#xa;    </xsl:text> 
    </xsl:copy>
  </xsl:template>

  <xsl:template match="@* | node()">
    <xsl:copy copy-namespaces="no">
      <xsl:apply-templates select="@* | node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template name="idFromName">
    <xsl:param name="pText"/>

    <xsl:variable name="oneDown">
      <xsl:call-template name="stripLast">
        <xsl:with-param name="pText" select="$pText"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:call-template name="stripLastWithRemove">
      <xsl:with-param name="pText" select="$oneDown"/>
    </xsl:call-template>
  </xsl:template>

  <xsl:template name="stripLast">
    <xsl:param name="pText"/>
    <xsl:param name="pDelim" select="'-'"/>

    <xsl:if test="contains($pText, $pDelim)">
      <xsl:value-of select="substring-before($pText, $pDelim)"/>
      <xsl:if test="contains(substring-after($pText, $pDelim), $pDelim)">
        <xsl:value-of select="$pDelim"/>
      </xsl:if>
      <xsl:call-template name="stripLast">
        <xsl:with-param name="pText" select=
          "substring-after($pText, $pDelim)"/>
        <xsl:with-param name="pDelim" select="$pDelim"/>
      </xsl:call-template>
    </xsl:if>
  </xsl:template>

  <xsl:template name="stripLastWithRemove">
    <xsl:param name="pText"/>
    <xsl:param name="pDelim" select="'-'"/>

    <xsl:if test="contains($pText, $pDelim)">
      <xsl:value-of select="substring-before($pText, $pDelim)"/>
      <xsl:call-template name="stripLastWithRemove">
        <xsl:with-param name="pText" select=
          "substring-after($pText, $pDelim)"/>
        <xsl:with-param name="pDelim" select="$pDelim"/>
      </xsl:call-template>
    </xsl:if>
  </xsl:template>
</xsl:stylesheet>
